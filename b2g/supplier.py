'''
Execution code for the supplier federate. The supplier subscribes to the secondary distribution
feeder's load and uses a simple supply curve function to generate a price.
'''
import helics as h
import pandas as pd

UNCONTROLLED = pd.read_csv('uncontrolled.csv', index_col=0).N2
MU = UNCONTROLLED.mean()
SIGMA = UNCONTROLLED.std()
MAX_SIGMA = 2
MAX_T = 60*60*24*31

fed = h.helicsCreateValueFederateFromConfig('input/supplier.json')
pub = h.helicsFederateGetPublicationByIndex(fed, 0)
sub = h.helicsFederateGetInputByIndex(fed, 0)

h.helicsFederateEnterInitializingMode(fed)
h.helicsPublicationPublishComplex(pub, MAX_SIGMA)

h.helicsFederateEnterExecutingMode(fed)

t = 0
while t < MAX_T:
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
