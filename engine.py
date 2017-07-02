#!/usr/bin/env python
# -*- coding: utf-8 -*-

# filter.py // Jeff Hobbs // May 2016
# create filtered set of recent news

import os
import sys
import logging
import json
import configparser
import argparse
import time
import arrow
import requests
import requests_cache

from urlparse import urlparse
from HTMLParser import HTMLParser

# set up logging, cache
PATH = os.path.dirname(os.path.abspath(__file__))
LOG_FILENAME = PATH + '/brightertimeline.log'
logging.basicConfig(filename=LOG_FILENAME,level=logging.CRITICAL)
requests_cache.install_cache(PATH + '/api-cache', expire_after=86400)

# set up API keys from external config apikeys.txt file
config = configparser.ConfigParser()
config.read(PATH + '/apikeys.txt')
NEWSAPIKEY = config.get('apikeys', 'newsapi_apikey')
MERCURYAPIKEY = config.get('apikeys', 'mercury_apikey')
SPARKPOST_APIKEY = config.get('apikeys', 'sparkpost_apikey')
FACEBOOK_APIKEY = config.get('apikeys', 'facebook_apikey')
TWITTER_CONSUMER_KEY = config.get('twitter', 'consumer_key')
TWITTER_CONSUMER_SECRET = config.get('twitter', 'consumer_secret')
TWITTER_ACCESS_TOKEN = config.get('twitter', 'access_token')
TWITTER_ACCESS_TOKEN_SECRET = config.get('twitter', 'access_token_secret')

# globals
NEWS_CATEGORIES = ["general", "technology", "entertainment", "gaming", "music", "science-and-nature", "business", "sport"]
URL_BLACKLIST = [".uk", "/wikis/", "www.aljazeera.com", "www.ft.com", "www.ladbible.com","www.sportbible.com","www.espncricinfo.com", "twitter.com"]
RESIZE_BLACKLIST = ["espncdn.com","aolcdn.com","guim.co.uk"]
FILTER = ["Trump"]
TIMESTAMP = time.strftime("%Y-%m-%d")
UBER_MANIFEST = []
MANIFEST = []
THUMBNAIL_WIDTH = "357"
IMAGE_MANIFEST = []

# set up filter term(s)
parser = argparse.ArgumentParser()
parser.add_argument('-f', '--filter', nargs='+', type=str, help='Filter on...', default=FILTER)
parser.add_argument('-c', '--categories', nargs='+', type=str, help='Categories...', default=NEWS_CATEGORIES)
ARGS = parser.parse_args()
FILTER = ARGS.filter
NEWS_CATEGORIES = ARGS.categories

# get the sources for articles
def getSources(category,language):
	global MANIFEST
	MANIFEST = []
	#example API call: https://newsapi.org/v1/sources?language=en&category=general
	parameters = {'category': category, 'language': language}
	r = requests.get('https://newsapi.org/v1/sources', params=parameters)
	data = r.json()
	for source in data["sources"]:
		name = source["name"]
		print "----\n" + name + "\n----"
		try:
			getArticles(source,category,name)
		except:
			print("Unexpected error:", sys.exc_info()[0])
			print bcolors.WARNING + "SOURCE ERROR" + bcolors.ENDC

# get URLs of articles from the source
def getArticles(source,category,name):
	#example API call: https://newsapi.org/v1/articles?source=the-next-web&sortBy=top&apiKey=05406b195c0d4f3ea2f9ba7ef05bb8be
	parameters = {'source': source["id"], 'sortBy': 'top', 'apiKey': NEWSAPIKEY}
	r = requests.get('https://newsapi.org/v1/articles', params=parameters)
	data = r.json()
	for article in data["articles"]:
		url = article["url"]
		title = article["title"]
		engagement = getFBData(url)
		if any(blacklisted_url in url for blacklisted_url in URL_BLACKLIST):
			print bcolors.WARNING + "BLACKLISTED URL: " + article["url"] + bcolors.ENDC
		else:
			parseArticle(article,engagement,category,name)

# make side trip to get engagement data
def getFBData(url):
	#example API call: https://graph.facebook.com/v2.2/?id=http://www.MY-LINK.com&fields=og_object{engagement}&access_token=<access_token>
	parameters = {'id': url, 'fields': 'og_object{engagement}', 'access_token': FACEBOOK_APIKEY}
	try:
		r = requests.get('https://graph.facebook.com/v2.2/', params=parameters)
		data = r.json()
		count = data["og_object"]["engagement"]["count"]
		return count
	except:
		return 0

# get content + metadata of article
def parseArticle(article,engagement,category,name):
	# example API call: https://mercury.postlight.com/parser?url=https://trackchanges.postlight.com/building-awesome-cms-f034344d8ed
	# requires apikey in x-api-key header	
	parameters = {'url': article["url"]}
	headers = {'x-api-key': MERCURYAPIKEY}
	r = requests.get('https://mercury.postlight.com/parser', params=parameters, headers=headers)
	data = r.json()
	try:
		title = data["title"]
		content = strip_tags(data["content"])
		if (any(filter_word in content for filter_word in FILTER) or any(filter_word in title for filter_word in FILTER)):
			print bcolors.FAIL + data["title"] + " [" + str(engagement) + "]" + bcolors.ENDC
		else:
			try:
				unix_timestamp = arrow.get(data["date_published"]).timestamp
			except:
				unix_timestamp = 0

			resized_lead_image_url = returnResizedImage(data["lead_image_url"])

			entry = {"title": data["title"], "url": data["url"], "excerpt": data["excerpt"], "domain": data["domain"], "date_published": data["date_published"], "unix_timestamp": unix_timestamp, "lead_image_url": data["lead_image_url"], "resized_lead_image_url": resized_lead_image_url["url"], "resized_lead_image_status_code": resized_lead_image_url["status_code"], "word_count": data["word_count"], "engagement": engagement, "category": category, "name": name}
			image_entry = {"resized_lead_image_url": resized_lead_image_url, "engagement": engagement, "word_count": data["word_count"], "unix_timestamp": unix_timestamp}
			
			UBER_MANIFEST.append(entry)
			MANIFEST.append(entry)
			IMAGE_MANIFEST.append(image_entry)

			print bcolors.OKGREEN + data["title"] + " [" + str(engagement) + "]" + bcolors.ENDC
	except:
		print bcolors.WARNING + "ARTICLE ERROR: " + article["url"] + bcolors.ENDC

def returnResizedImage(url):
	if any(blacklisted_url in url for blacklisted_url in RESIZE_BLACKLIST):
		return {'url':lead_image_url, 'status_code':200}
	else:
		full_lead_image_url = url
		parsed_lead_image_url = urlparse(full_lead_image_url)
		lead_image_url_domain = '{uri.scheme}://{uri.netloc}'.format(uri=parsed_lead_image_url)
		resized_lead_image_url_domain = lead_image_url_domain + ".rsz.io"
		resized_lead_image_url = full_lead_image_url.replace(lead_image_url_domain,resized_lead_image_url_domain) + "?width=" + THUMBNAIL_WIDTH
		resized_lead_image_url = resized_lead_image_url.replace("https","http")

		r = requests.get(resized_lead_image_url)
		status_code = r.status_code

		return {'url':resized_lead_image_url, 'status_code':status_code }

def writeJSON(category):
	ENGAGEMENT_UBER_MANIFEST = sorted(UBER_MANIFEST, key=lambda k: k.get('engagement', 0), reverse=True)
	ENGAGEMENT_MANIFEST = sorted(MANIFEST, key=lambda k: k.get('engagement', 0), reverse=True)

	WORD_COUNT_UBER_MANIFEST = sorted(UBER_MANIFEST, key=lambda k: k.get('word_count', 0), reverse=True)
	WORD_COUNT_MANIFEST = sorted(MANIFEST, key=lambda k: k.get('word_count', 0), reverse=True)

	UNIX_TIMESTAMP_UBER_MANIFEST = sorted(UBER_MANIFEST, key=lambda k: k.get('unix_timestamp', 0), reverse=True)
	UNIX_TIMESTAMP_MANIFEST = sorted(MANIFEST, key=lambda k: k.get('unix_timestamp', 0), reverse=True)

	if category is "all":


		with open(PATH + "/data/" + category + '_engagement.json', 'w') as outfile:
			json.dump(ENGAGEMENT_UBER_MANIFEST, outfile, indent=4, sort_keys=True, separators=(',', ':'))
		with open(PATH + "/data/" + category + '_word_count.json', 'w') as outfile:
			json.dump(WORD_COUNT_UBER_MANIFEST, outfile, indent=4, sort_keys=True, separators=(',', ':'))
		with open(PATH + "/data/" + category + '_unix_timestamp.json', 'w') as outfile:
			json.dump(UNIX_TIMESTAMP_UBER_MANIFEST, outfile, indent=4, sort_keys=True, separators=(',', ':'))

		print "----\nWRITING JSON FOR ALL..."
	else:

		with open(PATH + "/data/" + category + '_engagement.json', 'w') as outfile:
			json.dump(ENGAGEMENT_MANIFEST, outfile, indent=4, sort_keys=True, separators=(',', ':'))
		with open(PATH + "/data/" + category + '_word_count.json', 'w') as outfile:
			json.dump(WORD_COUNT_MANIFEST, outfile, indent=4, sort_keys=True, separators=(',', ':'))
		with open(PATH + "/data/" + category + '_unix_timestamp.json', 'w') as outfile:
			json.dump(UNIX_TIMESTAMP_MANIFEST, outfile, indent=4, sort_keys=True, separators=(',', ':'))


		print "----\nWRITING JSON FOR " + str(category) + "..."


# utility function(s)
# via: http://stackoverflow.com/questions/753052/strip-html-from-strings-in-python
class MLStripper(HTMLParser):
    def __init__(self):
        self.reset()
        self.fed = []
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return ''.join(self.fed)

def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()

# via: https://stackoverflow.com/questions/287871/print-in-terminal-with-colors-using-python
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# main function
if __name__ == '__main__':
	print "----"
	print "FILTERING STORES ON " + str(NEWS_CATEGORIES) + " BY " + str(FILTER)
	print "----"
	for category in NEWS_CATEGORIES:
		getSources(category,"en")
		writeJSON(category)
	writeJSON("all")
	print "----\nDONE."

	
