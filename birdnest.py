# Reaktor birdnest preassignment
# by Eve Kivivuori, January 2023
# This script is run as a daemon, and it runs in the background,
# continously updating the HTML file that the output for the user is in.
from math import sqrt
from time import sleep
from datetime import datetime, timedelta, timezone
import urllib.request
import urllib.error
# The XML libraries coming with python are vulnerable to entity explosion
# attacks, so we will use the defusedxml library.
import defusedxml.ElementTree as ET
import json
from time import perf_counter

# Hard-coded configuration section -- for such a small, single-use system
# this is fine, but for a more complex system I would use an .ini file or
# JSON or something, but that would then require stuff like extra error
# checking and there would probably need to be sensible defaults anyway --
# this way we are keeping it simple.
drone_data_url = 'http://assignments.reaktor.com/birdnest/drones'
pilot_data_url_prefix = 'http://assignments.reaktor.com/birdnest/pilots'
sleep_interval_seconds = 2
clearout_time_seconds = 10*60
(bird_x, bird_y) = (250_000, 250_000)
no_fly_zone_radius = 100_000 # units are millimeters, apparently
input_timestamp_format = '%Y-%m-%dT%H:%M:%S.%f%z'
output_timestamp_format = '%H:%M:%S %Z'
output_data_file = 'birdnest.json'

# The program itself.

def distance_from_bird(drone_x, drone_y):
    global bird_x, bird_y
    return sqrt((drone_x - bird_x) ** 2 + (drone_y - bird_y) ** 2)

def get_fresh_drone_data():
    global drone_data_url
    try:
        f = urllib.request.urlopen(drone_data_url)
    except urllib.error.URLError as err:
        print("URLError:", err.reason)
        return (None, None)
    else:
        if f.status != 200:
            return (None, None)
        raw_byte_data = f.read()
        stringified_data = raw_byte_data.decode(encoding='utf-8', errors='replace')
        root_element = ET.fromstring(stringified_data)
        capture_data = root_element.find('capture')
        if capture_data == None:
            return (None, None)
        capture_timestamp = capture_data.attrib['snapshotTimestamp']
        capture_time = datetime.strptime(capture_timestamp, input_timestamp_format)
        drones_in_this_capture = []
        for drone_element in capture_data:
            drone_data = {}
            for child_element in drone_element:
                drone_data[child_element.tag] = child_element.text
            pos_X_numeric = float(drone_data['positionX'])
            pos_Y_numeric = float(drone_data['positionY'])
            distance = distance_from_bird(pos_X_numeric, pos_Y_numeric)
            drone_data['distance'] = distance
            drones_in_this_capture.append(drone_data)
        return (capture_time, drones_in_this_capture)

def get_operator_details(drone_serial_number):
    global pilot_data_url_prefix
    request_uri = pilot_data_url_prefix + '/' + drone_serial_number
    try:
        f = urllib.request.urlopen(request_uri)
    except urllib.error.URLError as err:
        print("URLError:", err.reason)
        return None
    else:
        with f:
            if f.status != 200:
                return None
            stringified_data = f.read().decode(encoding='utf-8', errors='replace')
            return json.loads(stringified_data)


# The main loop: we will sit here, gathering data and writing it out.

# This dictionary will record the violators' drones' closest distances,
# and the last time the drone appeared at all in the 500-by-500 radar area.
violators = {}
# A cache of contact info, indexed by their drones' ID.
violator_contact_info = {}

while True:
    (timestamp, drone_data) = get_fresh_drone_data()
    if drone_data == None:
        print("Error fetching data at this time, trying again later.")
    else:
        start_time = perf_counter()
        for drone in drone_data:
            drone_name = drone['serialNumber']
            distance = drone['distance']
            if drone_name in violators:
                violators[drone_name]['last_seen'] = timestamp
            if drone['distance'] <= no_fly_zone_radius:
                if drone_name in violators:
                    if distance < violators[drone_name]['closest_distance']:
                        violators[drone_name]['closest_distance'] = distance
                else:
                    violators[drone_name] = {
                            'closest_distance': distance,
                            'last_seen': timestamp
                        }

        # Delete old data.
        ten_minutes_ago = datetime.now(timezone.utc) - timedelta(seconds=clearout_time_seconds)
        keys_to_remove = set()
        for drone_name in violators.keys():
            last_seen = violators[drone_name]['last_seen']
            if last_seen < ten_minutes_ago:
                keys_to_remove.add(drone_name)
        for key in keys_to_remove:
            del violators[key]

        # Build the output list. This will be written to a JSON file,
        # which the client will periodically retrieve.
        output_list = []
        for drone_id in sorted(violators):
            if (drone_id not in violator_contact_info
                    or violator_contact_info.get(drone_id) == None):
                # Fetch data for drone operators we haven't seen before, or who 404'd before.
                operator_info = get_operator_details(drone_id)
                violator_contact_info[drone_id] = operator_info

            operator_info = violator_contact_info[drone_id]
            closest_distance = violators[drone_id]['closest_distance']
            seen = violators[drone_id]['last_seen']
            readable_timestamp = seen.strftime(output_timestamp_format)
            d = {
                'id': drone_id,
                'dist': f"{closest_distance/1000:.1f}", # 10-cm resolution
                'seen': readable_timestamp
            }

            if operator_info == None:
                d['named'] = 0
            else:
                d['named'] = 1
                # This is untrusted input, so using .get() will solve key-not-found errors.
                d['name'] = operator_info.get('firstName', 'N/A') + ' ' + operator_info.get('lastName', 'N/A')
                d['phone'] = operator_info.get('phoneNumber', 'not given')
                d['email'] = operator_info.get('email', 'not given')
            output_list.append(d)

        # Do the outputting itself. Sort by most recent "visitors" first.
        sorted_list = sorted(output_list, key=lambda d: d['seen'], reverse=True)
        output_string = json.dumps(sorted_list)
        outfile = open(output_data_file, 'w')
        print(output_string, file=outfile)
        outfile.close()

        # Logging output to the terminal.
        print(f"{timestamp}: {len(drone_data)} drones, {len(violators)} violators, cache size {len(violator_contact_info)}.")
        #print("This iteration took", (perf_counter()-start_time), "seconds.\n")
    # Wait until there's new data available from the radar.
    sleep(sleep_interval_seconds)
