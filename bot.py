from __future__ import unicode_literals

import sys
import time
import collections

import telepot
from telepot.loop import MessageLoop
from telepot.delegate import pave_event_space, per_chat_id, create_open
from telepot.namedtuple import ReplyKeyboardMarkup, KeyboardButton
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton

from yelpapi import YelpAPI

import emoji

from motionless import DecoratedMap, LatLonMarker


# Credentials
TELEGRAM_TOKEN = '568558655:AAHhQeMgvaSSOvAnwxtRD-fbIvKUU_VZYjY'

YELP_API_KEY = 'Z-X7gH4iVODsOlnzPuoCbjg75d1XONY4Kh4YnvgSMucEqWL3wuCpjn6\
MKnjOul0TmPvmHAXUyOvhkRaUqO4KE-gR1jCkl18Phzqcy0rEUAMn-l5O9W8rUBHow60QW3\
Yx'

# BOT MESSAGES
WELCOME_MESSAGE = 'Welcome to BarBot. Find any bars nearby'
HELP_MESSAGE = '''Click button to find bars near your location. A map \
with all bars near your location is shown. Click in the inline buttons \
to get more information about the bar'''

# DEFAULT PARAMETERS
NUMBER_OF_BARS = 6
NUMBER_OF_OPTIONS_PER_ROW = 3
DELEGATOR_TIMEOUT = 1200

yelp_api = YelpAPI(YELP_API_KEY)

Bar = collections.namedtuple(
    'Bar',
    'name coordinates display_phone display_address rating')


def search_bars_nearby(latitude, longitude, limit):
    """This functions returns the bars near a specific location using
    the YELP API

    :param latitude: Latitude of the coordinate to search bars nearby
    :param longitude: Longitude of the coordinate to search bars nearby
    :param limit: Maximum number of bars to show

    :returns: list of bars
    """

    response = yelp_api.search_query(
        categories='bars',
        longitude=longitude,
        latitude=latitude,
        limit=limit)

    list_of_bars = []
    for business in response["businesses"]:
        rating = business["rating"]
        name = business["name"]
        coordinates = business["coordinates"]
        display_phone = business["display_phone"]
        city = business["location"]["city"]
        display_address = business["location"]["display_address"]

        if isinstance(display_address, list):
            display_address = "\n".join(display_address)

        bar = Bar(
            name=name,
            coordinates=coordinates,
            display_phone=display_phone,
            display_address=display_address,
            rating=rating
        )
        list_of_bars.append(bar)

    return list_of_bars


def create_map(center_lat, center_lon, markers):
    """Create the URL for a static google map centered in latitude
    `center_lat` and longitude `longitude`. It also shows in the map
    markers in the given coordinates labeled with numbers.


    :param center_lat: Latitude of the center of the map
    :param center_lon: Longitude of the center of the map
    :param markers: List of coordinates for the markers

    :returns: URL for static google map
    """

    google_map = DecoratedMap(
        lat=center_lat,
        lon=center_lon,
        zoom=15,
        size_x=400,
        size_y=400,
        maptype='roadmap',
        scale=1)

    for marker_index, marker in enumerate(markers, 1):
        google_map.add_marker(
            LatLonMarker(
                lat=marker["lat"],
                lon=marker["lon"],
                label=str(marker_index)
            )
        )

    url = google_map.generate_url()
    return url


class Bar_Bot_Handler(telepot.helper.ChatHandler):

    main_keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(
            text='Bars near my location',
            request_location=True)]
    ])

    def __init__(self, *args, **kwargs):
        super(Bar_Bot_Handler, self).__init__(*args, **kwargs)

    def on_chat_message(self, msg):
        content_type, chat_type, chat_id = telepot.glance(msg)

        if content_type == "location":
            location = msg["location"]

            longitude = location["longitude"]
            latitude = location["latitude"]

            self._list_of_bars = search_bars_nearby(latitude, longitude, limit=NUMBER_OF_BARS)

            inline_keyboard = []
            list_of_map_markers = []

            for i, bar in enumerate(self._list_of_bars, 1):
                bar_name = bar.name
                bar_rating = bar.rating

                if bar_rating.is_integer():
                    bar_rating = "%d" % bar_rating
                else:
                    bar_rating = "%1.1f" % bar_rating

                bar_text = "{option_number}. {bar_name}. :star: \
{bar_rating}".format(
                    option_number=i,
                    bar_name=bar_name,
                    bar_rating=bar_rating)

                bar_text = emoji.emojize(bar_text, use_aliases=True)

                list_of_map_markers.append({
                    "lat": bar.coordinates["latitude"],
                    "lon": bar.coordinates["longitude"]
                })

                inline_keyboard.append(
                    [
                        InlineKeyboardButton(
                            text=bar_text,
                            callback_data='bar_%s' % i
                        )
                    ]
                )

            map_url = create_map(latitude, longitude, list_of_map_markers)
            self._map_url = map_url

            self.sender.sendPhoto(map_url)

            self._inline_bar_selection_keyboard = InlineKeyboardMarkup(
                inline_keyboard=inline_keyboard
            )

            self.sender.sendMessage(
                "Select one option to get more information of the bar.",
                reply_markup=self._inline_bar_selection_keyboard)

            self._first_time = True

        elif content_type == "text":
            text = msg["text"].strip().lower()

            if text == "/start":
                self.sender.sendMessage(
                    WELCOME_MESSAGE,
                    reply_markup=self.main_keyboard
                )
                return

            if text == "/help":
                self.sender.sendMessage(HELP_MESSAGE)
                return

    def on_callback_query(self, msg):
        query_id, from_id, query_data = telepot.glance(
                                    msg,
                                    flavor='callback_query')

        # If data starts with 'bar_', then this means that the user
        # is asking more info for a bar.
        # Possible values are: bar_1, bar_2, bar_3,...

        if query_data.startswith("bar_"):

            if self._first_time:
                self._first_time = False
            else:
                self.sender.sendPhoto(self._map_url)

                # Send to telegram the menu of bars
                self.sender.sendMessage(
                    "Select a bar",
                    reply_markup=self._inline_bar_selection_keyboard
                )

            bar_index = int(query_data[4:]) - 1
            bar = self._list_of_bars[bar_index]

            # Send to telegram more information about the bar: phone,
            # address and geo location.
            text_for_bar_info = "*%s*" % bar.name

            if bar.display_phone:
                text_for_bar_info += "\n:telephone: {display_phone}\n".format(
                    display_phone=bar.display_phone)

            if bar.display_address:
                text_for_bar_info += "\n" + bar.display_address

            text_for_bar_info = emoji.emojize(
                text_for_bar_info,
                use_aliases=True)

            self.sender.sendMessage(
                text_for_bar_info,
                parse_mode="Markdown"
            )

            # Send to telegram the location of the bar
            if bar.coordinates:
                self._message_location = self.sender.sendLocation(
                    latitude=bar.coordinates["latitude"],
                    longitude=bar.coordinates["longitude"]
                )

bar_bot = telepot.DelegatorBot(TELEGRAM_TOKEN, [
    pave_event_space()(
        per_chat_id(),
        create_open,
        Bar_Bot_Handler,
        timeout=DELEGATOR_TIMEOUT,
        include_callback_query=True)
])
MessageLoop(bar_bot).run_as_thread()

while 1:
    time.sleep(10)
