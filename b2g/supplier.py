'''
Simulator for the supplier federate. The supplier subscribes to the secondary distribution
circuit's load and uses a simple supply curve function to generate a price.
'''
import helics as h
import pandas as pd

# Mean and standard deviation come from a run with a constant tolerance of 2 degrees Farenheit
# For analaysis, run stored in ./uncontrolled.csv
MU = 62992
SIGMA = 13291

# MAX_SIGMA is the z-score cutoff, meaning any demand level with a z score < -2 or > 2 will be
# clipped to those values
MAX_SIGMA = 2

# Number of seconds to run the simulation for
MAX_T = 60*60*24*31

# Create federate and get publication (price) and subscription (demand)
fed = h.helicsCreateValueFederateFromConfig('input/supplier.json')
pub = h.helicsFederateGetPublicationByIndex(fed, 0)
sub = h.helicsFederateGetInputByIndex(fed, 0)

# Initialize the federate and publish initial value; shouldn't matter what it is
h.helicsFederateEnterInitializingMode(fed)
h.helicsPublicationPublishComplex(pub, MAX_SIGMA)

h.helicsFederateEnterExecutingMode(fed)

t = 0
while t < MAX_T:
    # Control loop: read transformer load, compute z-score, publish price
    load = h.helicsInputGetDouble(sub)
    z_score = (load-MU)/SIGMA
    price = z_score + MAX_SIGMA
    price = (
        0 if price < 0
        else 2*MAX_SIGMA if price > 2*MAX_SIGMA
        else price
    )
    h.helicsPublicationPublishDouble(
        pub,
        price
    )
    t = h.helicsFederateRequestTime(fed, t+300)

# Close Helics federate
h.helicsFederateDisconnect(fed)
h.helicsFederateFree(fed)
h.helicsCloseLibrary()
