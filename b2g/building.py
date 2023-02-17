'''
Simulator for EnergyPlus residential building federate.
'''
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

# Set battery operation threshold prices
BAT_MAX_PRICE = 3.5
BAT_MIN_PRICE = 1.5

# Helics import statement must come AFTER state declaration to circumvent bug
import helics as h

def get_handle(state):
    '''
    Gets handle to the house's electricity meter, its cooling setpoint, and its heating setpoint.
    Run once at the beginning of a simulation.
    '''
    global HANDLE, CLG_SETP_HANDLE, HTG_SETP_HANDLE
    global CHG_SETP_HANDLE, DCH_SETP_HANDLE
    global BTY_SOC_HANDLE, BTY_CAP_HANDLE, POW_AVG_HANDLE
    HANDLE = api.exchange.get_meter_handle(
        state,
        "ElectricityPurchased:Facility".upper(),
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
    CHG_SETP_HANDLE = api.exchange.get_actuator_handle(
        state,
        "Schedule:Constant",
        "Schedule Value",
        "charge_schedule"
    )
    DCH_SETP_HANDLE = api.exchange.get_actuator_handle(
        state,
        "Schedule:Constant",
        "Schedule Value",
        "discharge_schedule"
    )
    BTY_SOC_HANDLE = api.exchange.get_variable_handle(
        state,
        "Electric Storage Simple Charge State",
        "SIMPLE_BATTERY"
    )
    BTY_CAP_HANDLE = api.exchange.get_variable_handle(
        state,
        "Schedule Value",
        "BATTERY_CAPACITY"
    )
    POW_AVG_HANDLE = api.exchange.get_variable_handle(
        state,
        "Schedule Value",
        "AVG_POWER"
    )

def control_loop(state):
    '''
    Reads the price from the supplier, sets the heating and cooling temperature setpoints, and
    publishes the facility-level electricity consumption to the secondary distribution federate.
    '''

    # EnergyPlus API callbacks can't take parameters other than the state, so input variables have
    # to be read in as global variables
    global t
    step = 60*15

    # We only want the control loop to be active during the primary run period, not sizing or
    # warmup runs. Otherwise, the timing with the grid-side federate would be thrown off.
    if (api.exchange.kind_of_sim(state) == 3) and not api.exchange.warmup_flag(state):

        # Read the price from the supplier
        price = h.helicsInputGetDouble(sub)

        # Read the power demand of the house
        demand = api.exchange.get_meter_value(state, HANDLE)/step

        # Set the temperature setpoint actuators as a function of the price.
        tolerance = 2 #(MAX_TOLERANCE/MAX_PRICE)*price*(5/9)
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

        # Set the energy storage (battery) setpoint actuators
        battery_cap = api.exchange.get_variable_value(state, BTY_CAP_HANDLE)
        battery_soc = api.exchange.get_variable_value(state, BTY_SOC_HANDLE)
        avg_power = api.exchange.get_variable_value(state, POW_AVG_HANDLE)

        # Function to set charge and discharge actuators
        # The schedules should never both be non-zero at a time
        # so this sets them both to 0 by default.
        # If the input is positive or negative,
        # the charge or discharge schedule is given
        # that value respectively.
        # Input: -1 to 1, inclusive
        def set_charge_discharge(amount = 0):
            api.exchange.set_actuator_value(
                state,
                CHG_SETP_HANDLE,
                0.0
            )
            api.exchange.set_actuator_value(
                state,
                DCH_SETP_HANDLE,
                0.0
            )
            if amount > 0:
                api.exchange.set_actuator_value(
                    state,
                    CHG_SETP_HANDLE,
                    min(amount, 1)
                )
            elif amount < 0:
                api.exchange.set_actuator_value(
                    state,
                    DCH_SETP_HANDLE,
                    min(abs(amount), 1)
                )

        soc = battery_soc/battery_cap
        shift = soc - 0.5 # -0.3 at empty, 0.3 at full
        cost_max = (BAT_MAX_PRICE - shift) * avg_power
        cost_min = (BAT_MIN_PRICE - shift) * avg_power
        cost_actual = price * demand
        overprice = 0

        if cost_max < cost_actual:
            overprice = (cost_max - cost_actual)/avg_power
        elif cost_min > cost_actual:
            overprice = (cost_min - cost_actual)/avg_power

        set_charge_discharge(overprice)

        h.helicsPublicationPublishComplex(
            pub,
            (demand)
        )
        t = h.helicsFederateRequestTime(fed, t+step)

# Get case name from command line argument
CASE = sys.argv[1]

# Create bulding federate
fed = h.helicsCreateValueFederateFromConfig(f'helics_config/{CASE}.json')
pub = h.helicsFederateGetPublicationByIndex(fed, 0)
sub = h.helicsFederateGetInputByIndex(fed, 0)

# Publish initial value
h.helicsFederateEnterInitializingMode(fed)
h.helicsPublicationPublishComplex(pub, 0)

# Schedule the callbacks - see EnergyPlus API documentation
api.runtime.callback_end_zone_sizing(state, get_handle)
api.runtime.callback_end_zone_timestep_after_zone_reporting(state, control_loop)

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
