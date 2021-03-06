# encoding: utf-8
import argparse
import os
import requests
import json
import datetime
import warnings
import functools
import operator
import sys
from requests.packages.urllib3 import exceptions
import pytz
import dateutil.parser
import caldav
from caldav.elements import dav, cdav
from icalendar import Calendar, Event, vText, vDatetime
from difflib import SequenceMatcher

from fuzzywuzzy import fuzz

# Ignore SSL errors

old_request = requests.request

#@functools.wraps(old_request)
def new_request(*args, **kwargs):
	kwargs['verify'] = False
	with warnings.catch_warnings():
		warnings.simplefilter("ignore", exceptions.InsecureRequestWarning)
		return old_request(*args, **kwargs)

requests.request = new_request

###
url = os.environ.get('CALDAV_URL')

now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)


def get_location(req):
	"""Reads locations.json and makes key lookupable by clinicName
	"""
	# Expand some tokens
	req = 'Centrum Medicover ' + req
	req = req.replace(u'Płd.', u'Południe')
	req = req.replace(' CM ', ' ')
	
	# Expand `req`
	with open('locations.json') as f:
		locations = json.load(f)
		matches = []
		for key, value in locations.items():
			# Expand key
			if value:
				expanded_key = u'{0} {1}'.format(key, value['cityname'])
			else:
				expanded_key = key
			ratio = fuzz.partial_ratio(req.lower(), expanded_key.lower())
			matches.append([key, ratio])
		matches.sort(key=operator.itemgetter(1))
		lookup_key, ratio = matches[-1]
		return locations[lookup_key]

def main():
	parser = argparse.ArgumentParser()
	parser.add_argument('-i', metavar='FILE_NAME', help='Input JSON file with appointments', required=True)
	parser.add_argument('-o', metavar='FILE_NAME', help='Output ICS file')
	parser.add_argument('--caldav', metavar='CALDAV_URL', help='URL of the CALDAV server')
	parser.add_argument('-p', '--person_name', metavar='NAME', help='Name to append to calendar entries')
	args = parser.parse_args()

	if not args.o and not url:
		print ('Provide -o command line argument for file output or CALDAV_URL environment variable ' +
				'for CalDAV output')
		parser.print_help()
		sys.exit(1)

	appointments = None

	with open(args.i) as f:
		appointments = json.load(f)

	# Generate vcal events from appointments
	icalendars = []
	all_events = Calendar()

	for appointment in appointments:
		cal = Calendar()
		location = get_location(appointment['clinicName'])
		dt = dateutil.parser.parse(appointment['appointmentDate'])
		tz = pytz.timezone('Europe/Warsaw')
		local = dt.replace(tzinfo=tz)
		event = Event()
		#event['methdo']
		event['uid'] = '{0}@medicover.pl'.format(appointment['id'])
		event['dtstart'] = vDatetime(local)
		event['dtend'] = vDatetime(local + datetime.timedelta(minutes=appointment['duration']))
		event['dtstamp'] = vDatetime(now)
		event['summary'] = vText(appointment['specializationName'])
		summary = appointment['specializationName']
		if args.person_name:
			summary += u' – {0}'.format(args.person_name)
		event['summary'] = vText(summary)
		event['description'] = vText(u'{0}, {1}'.format(
			appointment['specializationName'], appointment['doctorName']))
		event['class'] = 'private'

		if location:
			event['location'] = vText(u'{0}, {1}, {2}'.format(appointment['clinicName'], location['address'], location['cityname']))
			geocode = location['geocode']
			if geocode:
				event['geo'] = '{0};{1}'.format(*geocode['geo'])
		else:
			event['location'] = appointment['clinicName']
			
		cal.add_component(event)
		icalendars.append(cal)
		all_events.add_component(event)

	# Write calendar to file.
	if args.o:
		print 'Writing ' + args.o
		output_file = open(args.o, 'w')
		output_file.write(all_events.to_ical())

	# Write calendar to CalDAV.
	if url:
		client = caldav.DAVClient(url)
		principal = client.principal()
		calendars = principal.calendars()

		for calendar in calendars:
			name = calendar.get_properties([dav.DisplayName(),])['{DAV:}displayname']
			if name == 'Medicover':
				for cal in icalendars:
					print cal.to_ical()
					event = calendar.add_event(cal.to_ical())
					print 'Event', event, 'created'

	#for appointment in appointments:
		#print appointment['doctorName']
		#appointmentDate = dateutil.parser.parse(appointment['appointmentDate'])
		#print appointment['appointmentDate'], appointmentDate

if __name__ == '__main__':
	main()
