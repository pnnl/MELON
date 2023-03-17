'''
Simulator for the supplier federate. The supplier subscribes to the secondary distribution
circuit's load and uses a simple supply curve function to generate a price.
'''
import helics as h
import pandas as pd

# Mean and standard deviation come from a run with a constant tolerance of 2 degrees Farenheit
# For analaysis, run stored in ./uncontrolled.csv
MU = 62992 #39453 #
SIGMA = 13291 #16673 #

AVG_DATA = [[0, 63174.39055144579, 13205.62165931752],      # January
            [2976, 58775.32288074723, 17764.697533646267],  # February 
            [5760, 49046.54647177421, 14566.964075640322],  # etc.
            [8736, 40705.180771905434, 13485.639772502163],
            [11612, 33725.737701613005, 11112.602597785055],
            [14588, 28450.798020833303, 7407.8898923765855],
            [17468, 25956.07043010747, 4392.580330714608],
            [20444, 26068.13444220425, 4963.565909636013],
            [23420, 28689.98118055556, 6561.39814640322],
            [26300, 39437.124228187924, 10707.262639922124],
            [29280, 50318.59173611116, 13423.967745336065],
            [32160, 59240.65591397857, 11792.73232833755], # December
            [35136, 63174.39055144579, 13205.62165931752]] # "January", should never be used

# MAX_SIGMA is the z-score cutoff, meaning any demand level with a z score < -2 or > 2 will be
# clipped to those values
MAX_SIGMA = 2

# Number of seconds to run the simulation for
MAX_T = 60*60*24*366 #60*60*24*31

# Create federate and get publication (price) and subscription (demand)
fed = h.helicsCreateValueFederateFromConfig('input/supplier.json')
pub = h.helicsFederateGetPublicationByIndex(fed, 0)
sub = h.helicsFederateGetInputByIndex(fed, 0)

# Initialize the federate and publish initial value; shouldn't matter what it is
h.helicsFederateEnterInitializingMode(fed)
h.helicsPublicationPublishComplex(pub, MAX_SIGMA)

h.helicsFederateEnterExecutingMode(fed)

times = []
prices = []

t = 0
step = 60*5
current_month = 0
while t < MAX_T:
    # Control loop: read transformer load, compute z-score, publish price
    if t/(15*60) >= AVG_DATA[current_month+1][0]:
        current_month += 1
    
    load = h.helicsInputGetDouble(sub)
    z_score = (load-AVG_DATA[current_month][1])/AVG_DATA[current_month][2]    # (load-MU)/SIGMA
    price = z_score + MAX_SIGMA
    price = (
        0 if price < 0
        else 2*MAX_SIGMA if price > 2*MAX_SIGMA
        else price
    )

    times.append(t/60)
    prices.append(price)

    h.helicsPublicationPublishDouble(
        pub,
        price
    )
    t = h.helicsFederateRequestTime(fed, t+step)

# Close Helics federate
h.helicsFederateDisconnect(fed)
h.helicsFederateFree(fed)
h.helicsCloseLibrary()

# Print new price csv
data = {
    'time': times,
    'price': prices
}
df = pd.DataFrame(data)
df.to_csv('gridlab-d/price_log.csv', mode='w', index=False)
