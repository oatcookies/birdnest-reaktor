# Birdnest: a preassignment.

Implements [this assignment](https://assignments.reaktor.com/birdnest/):
shows the contact details of drone pilots who have recently flown their drones
too close to the simulated nest of an endangered _Gavia monadicus_ bird.
The assignment was rather simple, and in my view didn't require a complex solution,
so the implementation is only two files of code plus a third file created during deployment.

The deployment can be found [here](https://www.cs.helsinki.fi/u/macphee/birdnest.html).
The environment is at times a bit finicky (it's a busy multi-user shell access
server, with an occasionally-congested connection to networked storage),
and the output may occasionally be a few minutes out of date –
it should catch up soon enough, though.

## Structure

The architecture of this implementation is one of frequently-scheduled batch processing,
split between the server (`birdnest.py`) and the client (`birdnest.html`).
The communication between these happens via a third file, `birdnest.json`.
The client and the JSON file are statically served,
while the server is run as a daemon on a Linux box: "`nohup python3 birdnest.py &`".

Every two seconds or so, the server fetches new drone data from the monitoring station.
It parses the XML, calculates each drone's distance from the nest,
and keeps track of no-drone-zone–violating drones,
forgetting them after 10 minutes of being out of range of the _station_
(not after 10 minutes of leaving the zone).

For zone-violating drones, the server fetches the contact details of their
operators from the other endpoint; to reduce unnecessary network traffic,
it keeps a cache of all violators' contact details, which is particularly
easy because contact details were guaranteed to never change.
Finally, it will write the recent violators' details, drone IDs,
last-seen times, and distances from the nest to the `birdnest.json` file,
before sleeping for two seconds – the time for new data to appear.

This whole loop takes from about 1 to 5 milliseconds to run,
depending on how many contact detail fetches were done,
so the program spends over 99% of its time sleeping –
ideal for the shared environment it's deployed in.

The client (`birdnest.html`) fetches that `birdnest.json` file from the server,
and updates the displayed list with the data contained therein.
Every five seconds or so, it re-fetches the JSON file,
since it has probably updated in the meantime.
(The update interval was set to five seconds, instead of one or two, out of
consideration for the shared environment the system is deployed in.)

Because of the small volume of data, this file-sharing approach seemed best –
everything involves a tradeoff, of course, and the tradeoff here is
sacrificing real-time data display (which would need data streamed over a
websocket or something along those lines, needing a more robust server,
a more robust client, a messaging scheme, and so on)
for brute simplicity and "only" _near_-real-time data display.

