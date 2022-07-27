import sys

# EnergyPlus Python API
sys.path.insert(1, "/usr/local/EnergyPlus-9-5-0")
from pyenergyplus.api import EnergyPlusAPI

# Instantiate EnergyPlus API and state
api = EnergyPlusAPI()
state = api.state_manager.new_state()
HANDLE = None
CLG_SETP_HANDLE = None
HTG_SETP_HANDLE = None

# Set maximum price and temperature setpoint tolerance
MAX_PRICE = 4
MAX_TOLERANCE = 4

# Helics import statement must come AFTER state declaration to circumvent bug
import helics as h

def get_handle(state):
    '''
    Gets handle to the house's electricity meter
    '''
    global HANDLE, CLG_SETP_HANDLE, HTG_SETP_HANDLE
    HANDLE = api.exchange.get_meter_handle(
        state,
        "Electricity:Facility".upper(),
    )
    CLG_SETP_HANDLE = api.exchange.get_actuator_handle(
        state,
        "Schedule:Constant",
        "Schedule Value",
        "cooling_setpoint"
    )
    HTG_SETP_HANDLE = api.exchange.get_actuator_handle(
        state,
        "Schedule:Constant",
        "Schedule Value",
        "heating_setpoint"
    )

def log(state):
    '''
    Publishes the total electricity consumption of the house to the federation and sets the temperature setpoints
    '''
    global t, step
    if (api.exchange.kind_of_sim(state) == 3) and not api.exchange.warmup_flag(state):
        price = h.helicsInputGetDouble(sub)

        #### Control logic block ####
        tolerance = (MAX_TOLERANCE/MAX_PRICE)*price*(5/9)
        api.exchange.set_actuator_value(
            state,
            CLG_SETP_HANDLE,
            22.22 + tolerance
        )
        api.exchange.set_actuator_value(
            state,
            HTG_SETP_HANDLE,
            22.22 - tolerance
        )
        #############################

        p = api.exchange.get_meter_value(state, HANDLE)
        h.helicsPublicationPublishComplex(
            pub,
            (p/900)
        )
        t = h.helicsFederateRequestTime(fed, t+(15*60))

# Get case name from command line argument
CASE = sys.argv[1]

# Create bulding federate
fed = h.helicsCreateValueFederateFromConfig(f'helics_config/{CASE}.json')
pub = h.helicsFederateGetPublicationByIndex(fed, 0)
sub = h.helicsFederateGetInputByIndex(fed, 0)

# Publish initial value
h.helicsFederateEnterInitializingMode(fed)
h.helicsPublicationPublishComplex(pub, 0)

# Request next time at the end of each zone timestep after zone reporting
api.runtime.callback_end_zone_sizing(state, get_handle)
api.runtime.callback_end_zone_timestep_after_zone_reporting(state, log)

# Run the simulation
h.helicsFederateEnterExecutingMode(fed)
t = h.helicsFederateRequestTime(fed, 0)
api.runtime.run_energyplus(
    state = state,
    command_line_args = [
        '-d', f'output/{CASE}',
        '-w', '../input/USA_WA_Seattle-Tacoma.Intl.AP.727930_TMY3.epw',
        f'idf/{CASE}.idf'
    ]
)

# Close Helics federate
h.helicsFederateDisconnect(fed)
h.helicsFederateFree(fed)
h.helicsCloseLibrary()
