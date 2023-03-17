'''
Produces processed input files from the unprocessed input files in input/
'''
import os
import sys
import json
import glm
import pandas as pd
from eppy.modeleditor import IDF

# The IDD file is necessary for eppy. The versions must match.
IDF.setiddname('input/Energy+V9_5_0.idd')

# The filename for the top-level secondary GridLAB-D model found in /input, consistant with
# its name in the gridlabd/Taxonomy_Feeders repository.
GRIDLABD_FNAME = 'TopoCenter-PP_base.glm'

# Simulation specifications
# Includes: scenario flags; start and end dates; battery specs
SPECS = {
    'flags': {
        'controlled': 0,
        'heating': 0,
        'battery': 0
    },
    'timeframe': {
        "BEGIN_MONTH": 1,
        "BEGIN_DAY": 1,
        "END_MONTH": 1,
        "END_DAY": 31,
        "DURATION": 31
    },
    'heating_specs': {
        "IDEAL": 20
    },
    'battery_specs': {
        'energy_area_ratio': 2500 * 3600 * 10.7639, # KWh / sq.ft. (in m^2); 10.7639 ft^2 = 1 m^2
        'efficiency_charge': 0.85,
        'efficiency_discharge': 0.85,
        'power_charge': 1000,
        'power_discharge': 1000,
        'soc_initial': 0.5,
        'soc_max': 0.8,
        'soc_min': 0.2
    }
    }


# All the directories holding processed input and output that need to be created by this script.
SIM_DIRS = [
    'energyplus/idf',
    'energyplus/helics_config',
    'energyplus/output',
    'energyplus/schedules',
    'gridlab-d',
    'helics'
]

# Create necessary directories
for directory in SIM_DIRS:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Load JSON/GLM input files
with open('input/building_config.json', encoding='utf-8') as file:
    building_config = json.load(file)

with open('input/secondary.json', encoding='utf-8') as file:
    secondary = json.load(file)

with open('input/subscription.json', encoding='utf-8') as file:
    subscription = json.load(file)
info = json.loads(subscription['info'])

with open('input/run.json', encoding='utf-8') as file:
    run = json.load(file)

with open('input/federate.json', encoding='utf-8') as file:
    federate = json.load(file)


# Primary function to process inputs.
# Modifications to files should be added as functions (with a logical check, if necessary)
def process_input(base_specs):
    '''
    Main function. Called automatically when the script is run.
    Calls all other functions in the script.
    '''
    # This reads in the specification file provided
    # 1: Check if the new specs are truly new
    # 2: Collect the spec sections from the new file
    # 3: Collect the individual specs included in those sections
    # 4: Overwrite base specs with the new specs
    new_specs = read_sys_args()
    if new_specs != SPECS:
        for dict_key, dict_value in new_specs.items():
            for key, value in dict_value.items():
                base_specs[dict_key][key] = value

    flags = base_specs['flags']
    means = None
    if flags['controlled']:
        means = load_means('uncontrolled_mean_data.csv')

    [gld, triplex_loads] = modify_gld()

    house = [load['name'] for load in triplex_loads]
    for fname in os.listdir('input/idf'):
        case = fname.replace('.idf','')

        # Load IDF
        idf = IDF(f'input/idf/{case}.idf')

        ep_modify(idf, case)

        if flags['controlled']:
            ep_add_means(idf, means[case])

        if flags['heating']:
            ep_add_temperature_control(idf)

        if flags['battery']:
            ep_add_battery(idf, base_specs['battery_specs'])

        # Save modified IDF
        idf.saveas(f'energyplus/idf/{fname}')

        # Create the building HELICS federate configuration file
        building_config['name'] = case
        with open(f'energyplus/helics_config/{case}.json', 'w', encoding='utf-8') as _file:
            json.dump(building_config, _file, indent=4)

        # Add the building subscription to the secondary HELICS configuration file
        info['object'] = house.pop(0)
        subscription['key'] = f'{case}/electricity_consumption'
        subscription['info'] = json.dumps(info)
        secondary['subscriptions'].append(subscription.copy())

        # Add the building federate to the HELICS CLI configuration file
        federate['exec'] = f'python ../building.py {case}'
        federate['name'] = case
        run['federates'].append(federate.copy())

    setup_helics(gld)


# Function to read arguments from the command line.
# Used in conjunction with the process_input(...) function
def read_sys_args():
    '''
    Read input, if any, and process .json specification file
    '''
    if len(sys.argv) == 1:
        return SPECS

    if (file_in := sys.argv[1])[-5:] == '.json':
        print(f'Filename {file_in} accepted.')
        chosen_path = file_in
        with open(f'{chosen_path}', encoding='utf-8') as _file:
            spec_file = json.load(_file)
            print(f'File {chosen_path} loaded successfully.')
        return spec_file

    suffix = 'None'
    if '.' in file_in:
        suffix = '.'+file_in.split('.', 1)[1]
    print(f'Argument must have a .json suffix. Suffix provided: {suffix}')
    print('Using default specifications instead.')
    return SPECS


# Functions that prepare files found below.
def modify_gld():
    '''
    Modifies GLD
    '''
    gld = glm.load(f'input/{GRIDLABD_FNAME}')
    timeframe = SPECS['timeframe']

    # Add the 'connection' model to the GLM file. This module contains the 'helics_msg' object
    # necessary for HELICS integration
    gld['modules'].append(
        {
            'name': 'connection',
            'attributes': {}
        }
    )

    # Set the run period for GridLAB-D
    gld['clock']['starttime'] = f"2000-{timeframe['BEGIN_MONTH']}-{timeframe['BEGIN_DAY']} 00:00:00"
    gld['clock']['stoptime'] = f"2000-{timeframe['END_MONTH']}-{timeframe['END_DAY']} 23:59:00"

    # Add a 'helics_msg' object to the GLM pointing to the HELICS configuration file for the
    # secondary federate.
    gld['objects'].append(
        {
            'name': 'helics_msg',
            'attributes': {
                'name': 'secondary',
                'configure': 'secondary.json'
            },
            'children': []
        }
    )

    # Make two modifications to the GLM objects:
    # 1. Point the climate object to the weather file
    # 2. Replace 'house' objects with 'triplex_load' objects, keeping the same name and parent
    for gld_obj in gld['objects']:
        if gld_obj['name'] == 'climate':
            gld_obj['attributes']['tmyfile'] = '../input/CA-Sacramento.tmy2'
        elif gld_obj['name'] == 'house':
            gld_obj['name'] = 'triplex_load'
            gld_obj['attributes'] = {
                key: value for key, value in gld_obj['attributes'].items()
                if key in ['name', 'parent']
            }
            gld_obj['children'] = []
        elif gld_obj['name'] == 'solar':
            gld_obj['attributes'] = {
            key: value for key, value in gld_obj['attributes'].items()
            if key in ['name','parent','panel_type','efficiency','area']
        }

    # Modify two predefined output recorder objects:
    # 1. Voltage output: real and imaginary parts of all 10 buildings
    # 2. Power output: real power consumption of all 10 buildings plus the distribution transformer
    triplex_loads = [obj['attributes'] for obj in gld['objects'] if obj['name'] == 'triplex_load']
    for gld_obj in gld['objects']:
        if gld_obj['name'] == 'multi_recorder':
            if gld_obj['attributes']['file'] == 'Volt_log.csv':
                gld_obj['attributes']['property'] = ','.join(
                    [
                        f"{load['parent']}:measured_voltage_1.real,"
                        + f"{load['parent']}:measured_voltage_1.imag"
                        for load in triplex_loads
                    ]
                )
            elif gld_obj['attributes']['file'] == 'power_log.csv':
                gld_obj['attributes']['property'] = ','.join(
                    ['N2:measured_real_power'] + [
                        f"{load['parent']}:measured_real_power"
                        for load in triplex_loads
                    ]
                )
            gld_obj['attributes']['interval'] = 15*60
            gld_obj['attributes'].pop('limit')

    # Delete the house output, as we have replaced the GridLAB-D houses with external EnergyPlus
    # models.
    gld['objects'] = [
        obj for obj in gld['objects']
        if (obj['name'] != 'multi_recorder') or (obj['attributes']['file'] != 'House_log.csv')
    ]

    # Hard-code bldg_hvac_operation_sch to 1 all the time
    for fname in os.listdir('input/schedules'):
        dframe = pd.read_csv(f'input/schedules/{fname}', index_col = 0)
        dframe['bldg_hvac_operation_sch'] = 1
        dframe.to_csv(f'energyplus/schedules/{fname}')

    return [gld, triplex_loads]

# Read in data from the supplied file, if it exists
# For future designs, it might be interesting to have an uncontrolled variable/flag
# that disables the setpoint controls and storage features, so that new IDFs can be
# swapped in and quickly generate a new uncontrolled run.
def load_means(_path='uncontrolled.csv'):
    '''
    Creates a table of mean power demand for each building.
    Each entry in the table will be a list of mean power demands, corresponding to each simulated month. \n
    By default, it calculates the mean load from "uncontrolled.csv".
    If a different file is supplied, it will read in the means from that file instead. \n
    Function is hardcoded to match the site names at the moment.
    TODO: Find a way to have them not be hardcoded?
    '''
    means_table = {
        'SITE_00002': 'N3',#941.5245171297555, #N3
        'SITE_00003': 'N4',#2568.0198817129635, #N4
        'SITE_00004': 'N6',#7763.370347453871, #N6
        'SITE_00005': 'N7',#9418.06025115738, #N7
        'SITE_00006': 'N9',#6359.274783333475, #N9
        'SITE_00007': 'N10',#10065.708789351762, #N10
        'SITE_00008': 'N11',#2622.3587423610675, #N11
        'SITE_00009': 'N12',#8922.142683564769, #N12
        'SITE_00010': 'N13',#2698.1558887732117, #N13
        'SITE_00011': 'N14'#4930.715833564907, #N14
    }

    if os.path.exists(_path):
        file_in = pd.read_csv(_path, index_col=0)
        for site_name, node_num in means_table.items():
            if _path == 'uncontrolled.csv':
                _mean = [file_in[node_num].mean()]
            else:
                _mean = list(file_in[node_num])
            means_table[site_name] = _mean

    return means_table

## Define functions to modify EnergyPLUS .idf files

def ep_modify(_idf, case):
    '''Prepares idf files for simulation.'''
    timeframe = SPECS['timeframe']
    # Set EnergyPlus run period
    run_period = [
        run_period for run_period in _idf.idfobjects['RUNPERIOD']
        if run_period['Name'] == 'Run Period 1'
    ]
    run_period = run_period[0] if len(run_period) == 1 else None
    run_period['Begin_Month'] = timeframe['BEGIN_DAY']
    run_period['Begin_Day_of_Month'] = timeframe['BEGIN_DAY']
    run_period['End_Month'] = timeframe['END_MONTH']
    run_period['End_Day_of_Month'] = timeframe['END_DAY']

    # Set Variable Dictionary output type ('regular' or 'IDF')
    var_dictionary = _idf.getobject('OUTPUT:VARIABLEDICTIONARY','Regular')
    var_dictionary['Key_Field'] = 'IDF'

    # Point SCHEDULE:FILE objects to schedule CSVs
    for schedule in _idf.idfobjects['SCHEDULE:FILE']:
        path = f'schedules/{case}_schedules.csv'
        schedule['File_Name'] = (
            path if path in schedule['File_Name'] else schedule['File_Name']
        )

    # Add the Electricity:Purchased meter
    # This automatically subtracts on-site energy (storage, generators)
    # from the default meter (i.e., it reports the actual demand on the grid)
    purchased = _idf.newidfobject('OUTPUT:METER')
    purchased['Key_Name'] = 'ElectricityPurchased:Facility'
    purchased['Reporting_Frequency'] = 'Timestep'

def ep_add_means(_idf, mean_list):
    '''
    Function to add mean energy consumption outputs. \n
    If mean_list has a length of 1, a constant schedule is added. \n
    Otherwise, it is assumed mean_list has a length of 12 and a compact schedule is added for the whole year
    '''
    if len(mean_list) == 1:
        avg_power = _idf.newidfobject('SCHEDULE:CONSTANT')
        avg_power['Name'] = 'avg_power'
        avg_power['Schedule_Type_Limits_Name'] = 'Any Number'
        avg_power['Hourly_Value'] = mean_list[0]
    else:
        avg_power = _idf.newidfobject('SCHEDULE:COMPACT')
        avg_power['Name'] = 'avg_power'
        avg_power['Schedule_Type_Limits_Name'] = 'Dimensionless'
        dates = ['1/31', '2/29', '3/31', '4/30',
                 '5/31', '6/30', '7/31', '8/31',
                 '9/30', '10/31', '11/30', '12/31']
        for i in range(12):
            avg_power[f'Field_{4*i+1}'] = f'Through: {dates[i]}'
            avg_power[f'Field_{4*i+2}'] = 'For: AllDays'
            avg_power[f'Field_{4*i+3}'] = 'Until: 24:00'
            avg_power[f'Field_{4*i+4}'] = mean_list[i]

    avg_out = _idf.newidfobject('OUTPUT:VARIABLE')
    avg_out['Key_Value'] = 'avg_power'
    avg_out['Variable_Name'] = 'Schedule Value'
    avg_out['Schedule_Name'] = 'avg_power'

def ep_add_temperature_control(_idf):
    '''Adds heating and cooling setpoints for use in a controlled scenario.'''
    # Create new SCHEDULE:CONSTANT objects for the heating and cooling setpoints. These will be
    # actuated by the EnergyPlus Python API. 20 Celsius will be our default value.
    cooling_setpoint = _idf.newidfobject('SCHEDULE:CONSTANT')
    heating_setpoint = _idf.newidfobject('SCHEDULE:CONSTANT')
    cooling_setpoint['Name'] = 'cooling_setpoint'
    cooling_setpoint['Schedule_Type_Limits_Name'] = 'Any Number'
    cooling_setpoint['Hourly_Value'] = 20
    heating_setpoint['Name'] = 'heating_setpoint'
    heating_setpoint['Schedule_Type_Limits_Name'] = 'Any Number'
    heating_setpoint['Hourly_Value'] = 20

    # Point the DUALSETPOINT object to the SCHEDULE:CONSTANT objects
    setpoint = _idf.idfobjects['THERMOSTATSETPOINT:DUALSETPOINT']
    setpoint = setpoint[0] if len(setpoint) == 1 else None
    setpoint['Heating_Setpoint_Temperature_Schedule_Name'] = 'heating_setpoint'
    setpoint['Cooling_Setpoint_Temperature_Schedule_Name'] = 'cooling_setpoint'

def ep_add_battery(_idf, stats):
    '''
    Adds battery objects to a specific EnergyPLUS .idf file.
    - _idf: An .idf file opened through eppy.modeleditor.IDF()
    - stats: A dictionary that describes the functionality of a Simple Battery object.
        - Keys:
        energy_area_ratio, efficiency_charge, efficiency_discharge,
        power_charge, power_discharge, soc_initial, soc_max, soc_min
        - Read in from a sim_specs_X.json file specified when run from the command line.
            - If no file is specified, a default file is chosen.
    '''
    # We are interested to see how storage affects a connected community, so a simple
    # storage apporximation will be sufficient for our simulation.
    # As informed by Jerry, buildings generally have battery sizes that
    # correlate to their floor area. The relationship is currently
    # 2.5 kWh/sqft, but may go up to 5.0 kWh/sqft.

    floor_area = 0
    for floor_zone in _idf.idfobjects['CONSTRUCTION:FFACTORGROUNDFLOOR']:
        floor_area += floor_zone['Area'] # EPlus uses m^2
    energy_requirement = stats['energy_area_ratio'] * floor_area

    battery = _idf.newidfobject('ELECTRICLOADCENTER:STORAGE:SIMPLE')
    battery['Name'] = 'simple_battery'
    battery['Nominal_Energetic_Efficiency_for_Charging'] = stats['efficiency_charge']
    battery['Nominal_Discharging_Energetic_Efficiency'] = stats['efficiency_discharge']
    battery['Maximum_Storage_Capacity'] = energy_requirement
    battery['Maximum_Power_for_Discharging'] = stats['power_discharge']
    battery['Maximum_Power_for_Charging'] = stats['power_charge']
    battery['Initial_State_of_Charge'] = energy_requirement * stats['soc_initial']

    # Add output for the state of charge of the storage
    # Useful for creating control logic in the building.py script
    soc = _idf.newidfobject('OUTPUT:VARIABLE')
    soc['Variable_Name'] = 'Electric Storage Simple Charge State'
    soc['Reporting_Frequency'] = 'Timestep'

    capacity_const = _idf.newidfobject('SCHEDULE:CONSTANT')
    capacity_const['Name'] = 'battery_capacity'
    capacity_const['Schedule_Type_Limits_Name'] = 'Any Number'
    capacity_const['Hourly_Value'] = energy_requirement

    capacity_out = _idf.newidfobject('OUTPUT:VARIABLE')
    capacity_out['Key_Value'] = 'battery_capacity'
    capacity_out['Variable_Name'] = 'Schedule Value'
    capacity_out['Schedule_Name'] = 'battery_capacity'

    # These modify the (dis)charging rates. Both 0 to 1, inclusive.
    # These modify the rate at which the battery is (dis)charged,
    # based on the designed power rates.
    # Only one of these should be non-zero at a time.
    # Logic control found in the building.py script
    charge_schedule = _idf.newidfobject('SCHEDULE:CONSTANT')
    charge_schedule['Name'] = 'charge_schedule'
    charge_schedule['Schedule_Type_Limits_Name'] = 'Any Number'
    charge_schedule['Hourly_Value'] = 0.0
    discharge_schedule = _idf.newidfobject('SCHEDULE:CONSTANT')
    discharge_schedule['Name'] = 'discharge_schedule'
    discharge_schedule['Schedule_Type_Limits_Name'] = 'Any Number'
    discharge_schedule['Hourly_Value'] = 0.0

    # Add the distribution object
    # Mode: AC w/ Storage;
    # Required objects:
    # Converter (created below)
    # Storage (Simple storage; above)
    # Schedules (Charge and Discharge; above)
    converter = _idf.newidfobject('ELECTRICLOADCENTER:STORAGE:CONVERTER')
    converter['Name'] = 'converter'
    converter['Power_Conversion_Efficiency_Method'] = 'SimpleFixed'
    converter['Simple_Fixed_Efficiency'] = 1

    distribution = _idf.newidfobject('ELECTRICLOADCENTER:DISTRIBUTION')
    distribution['Name'] = 'distribution'
    distribution['Electrical_Buss_Type'] = 'AlternatingCurrentWithStorage'
    distribution['Electrical_Storage_Object_Name'] = 'simple_battery' # Storage object
    distribution['Storage_Operation_Scheme'] = 'TrackChargeDischargeSchedules'
    distribution['Storage_Converter_Object_Name'] = 'converter' # Converter object
    distribution['Maximum_Storage_State_of_Charge_Fraction'] = stats['soc_max']
    distribution['Minimum_Storage_State_of_Charge_Fraction'] = stats['soc_min']
    distribution['Design_Storage_Control_Charge_Power'] = stats['power_charge']
    distribution['Storage_Charge_Power_Fraction_Schedule_Name'] = 'charge_schedule' # Schedule
    distribution['Design_Storage_Control_Discharge_Power'] = stats['power_discharge']
    distribution['Storage_Discharge_Power_Fraction_Schedule_Name'] = 'discharge_schedule' # Schedule

def setup_helics(gld):
    '''
    Create the secondary GLM file, secondary HELICS configuration file, and HELICS CLI
    configuration file
    '''
    with open(f'gridlab-d/{GRIDLABD_FNAME}', 'w', encoding='utf-8') as _file:
        _file.write(glm.dumps(gld).replace('"', "'", 4))

    with open('gridlab-d/secondary.json', 'w', encoding='utf-8') as _file:
        json.dump(secondary, _file, indent=4)

    with open('helics/run.json', 'w', encoding='utf-8') as _file:
        json.dump(run, _file, indent=4)

process_input(SPECS)
