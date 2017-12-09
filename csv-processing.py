import json
import urllib2
import requests
import threading
import time
import os

# lock on the post_obj for multithreading purposes
POST_DICT_LOCK = threading.Lock()

# article_name -> wp_post_obj
post_obj = {}

def main():
    """Primary method that processes the CSV data for our Cornell Sun 
    age classifier."""
    global post_obj

    # article_title -> {age_range -> total_sessions}
    temp_dict = build_article_dict()
    # (hashed_dict, total_sessions) = dict_into_buckets(temp_dict)

    # age_group -> number_sessions
    total_sessions = count_sessions_by_age(temp_dict)

    # article_title -> popular_age_range
    classifications = classify_articles(temp_dict, total_sessions)

    if os.path.isfile("postsdata.txt"):
        with open("postsdata.txt", "r") as data_file:
            post_obj = json.loads(data_file.read())
    else:
        # populates global post_obj dictionary
        retrieve_post_information(classifications)
        with open("postsdata.txt", "w+") as data_file:
            json.dump(post_obj, data_file)

    training_data = build_training_data(post_obj)
    print training_data

    with open("training_data.txt", "w+") as data_file:
        json.dump(training_data, data_file)
    print "DONE :)"

def build_article_dict():
    """Read in the first CSV and sort all entries into article buckets."""
    temp_dict = {}
    with open("sun-classifier-data/sun-article-sessions.csv") as csv_file:
        count = 0
        for line in csv_file.readlines():
            if count < 8:
                count += 1
                continue  # skip headers
            if count == 5007:
                break  # bottom data not formatted properly
            count += 1

            # example line:
            # 55-64,"""WANG | The Seven Degrees of Cornell""",14,0,0,0,0,14
            entry = line.split(',"""')
            age_range = entry[0].strip()
            second_entry = entry[1].split('""",')
            article_name = second_entry[0]
            article_name = article_name[:article_name.rfind("|")].strip().decode("utf8", "ignore")
            sessions = second_entry[1].split(",")
            total_sessions = int(sessions[0].strip())

            if article_name in temp_dict:
                # article already in dict
                article_entry = temp_dict[article_name]
                if age_range in article_entry:
                    # age group represented in dict -> increment
                    article_entry[age_range] += total_sessions
                else:
                    # age range not represented -> set equal to #sessions
                    article_entry[age_range] = total_sessions
            else:
                # article name not represented
                temp_dict[article_name] = { age_range: total_sessions }
    return temp_dict

def dict_into_buckets(articles):
    """Group ages into buckets as defined in writeup. Currently hashes into
    buckets by adding all the smaller age group sessions into the larger
    bucket, which skews the information towards generally larger buckets."""
    bucket_dict = {}
    total_sessions = {
        '18-24': 0,
        '25-44': 0,
        '45+': 0
    }
    for article_name in articles:
        ranges = articles[article_name]
        article_ranges_dict = {
            '18-24': 0,
            '25-44': 0,
            '45+': 0
        }
        for group in ranges:
            # Hash into 18-24, 25-44, or 45+
            if group == '18-24':
                article_ranges_dict['18-24'] += ranges[group]
                total_sessions['18-24'] += ranges[group]
            elif group == '25-34' or group == '35-44':
                article_ranges_dict['25-44'] += ranges[group]
                total_sessions['25-44'] += ranges[group]
            else:
                article_ranges_dict['45+'] += ranges[group]
                total_sessions['45+'] += ranges[group]

        bucket_dict[article_name] = article_ranges_dict
    return (bucket_dict, total_sessions)

def count_sessions_by_age(articles):
    """Count how many sessions in each age group."""
    total_sessions = {}
    for article_name in articles:
        sessions_by_age = articles[article_name]
        for age_group in sessions_by_age:
            sessions = sessions_by_age[age_group]
            if age_group in total_sessions:
                total_sessions[age_group] += sessions
            else:
                total_sessions[age_group] = sessions
    return total_sessions

def classify_articles(articles, sessions):
    """Return dictionary of ArticleName: AgeGroupClassification depending on 
    number of sessions per article."""
    classification_dict = {}

    for article in articles:
        buckets = articles[article]
        opt_bucket = None
        opt_bucket_sessions = 0.0

        # get age_range with largest num sessions
        for age_group in buckets:
            if buckets[age_group] > opt_bucket_sessions:
                opt_bucket = age_group
                opt_bucket_sessions = buckets[age_group]

        # hash into one of the three buckets as classification
        if opt_bucket == '18-24':
            opt_bucket = '18-24'
        elif opt_bucket == '25-34' or opt_bucket == '35-44':
            opt_bucket = '25-44'
        else:
            opt_bucket = '45+'

        classification_dict[article] = opt_bucket
    return classification_dict

def wp_request_article(article):
    """Search for the wordpress Post object from the REST API given the article
    name."""
    article = article.decode("utf8", "ignore")
    url = "http://cornellsun.com/wp-json/wp/v2/posts?search={}".format(article)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.102 Safari/537.36'
    }
    with requests.get(url, headers=headers) as wp_response:
        # print wp_response.text
        print wp_response.text
        if wp_response.text == "[]":
            # no responses for this article :(
            # print "No articles found for article: {}".format(article)
            print "RETURNING EARLY"
            return
        try:
            wp_post = json.loads(wp_response.text)
        except:
            print "EXCEPTION RAISED"
            return
        # print wp_response.text
        wp_single_post = None
        if "title" not in wp_post[0]:
            # title not found?
            # print "No article title found for article: {}".format(article)
            return
        elif article != wp_post[0]["title"]["rendered"]:
            # titles not equal, no bueno
            return
        else:
            # should be valid
            wp_single_post = wp_post[0]
        if not wp_single_post is None:
            with POST_DICT_LOCK:
                post_obj[article] = wp_single_post

def retrieve_post_information(classifications):
    """Run requests on multiple threads to the Wordpress backend. Retrieves the
    closest match (if possible) to the unicode title and populates a dictionary
    from the article title to the object."""
    threads = []
    for article in classifications:
        thread = threading.Thread(target=wp_request_article, args=[article])
        threads.append(thread)

    for thread in threads:
        thread.start()
        time.sleep(0.75)

    for thread in threads:
        thread.join(30.0)

def build_training_data(posts):
    """Evaluates the features for this article post and stores them in a dict."""
    training_data = {}
    for article in posts:
        post_obj = posts[article]
        features = _build_feature_dict(post_obj)
        training_data[article] = features
    return training_data


def _build_feature_dict(post):
    """Return a dictionary of features for a given post object."""
    features = {}
    article_title = post["title"]["rendered"]
    features["title_length"] = len(article_title)
    features["categories"] = ', '.join(post["category_strings"])
    features["tags"] = ', '.join(post["tag_strings"])
    features["content_size"] = len(post["content"]["rendered"])
    features["num_images"] = len(post["post_attachments_meta"])
    features["primary_category"] = post["primary_category"]

    num_words = len(article_title.split(" "))
    features["average_word_length_title"] = len(article_title) / num_words

    pipe_index = article_title.find("|")
    if pipe_index == -1:
        pipe_index = len(article_title)
    features["title_split_on_pipe"] = article_title[:pipe_index].strip()
    return features

if __name__ == '__main__':
    main()