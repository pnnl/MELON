'''
Produces processed input files from the unprocessed input files in input/
'''
import os
import json
import glm
import pandas as pd
from eppy.modeleditor import IDF

# The IDD file is necessary for eppy. The versions must match.
IDF.setiddname('input/Energy+V9_5_0.idd')

# The filename for the top-level secondary GridLAB-D model found in /input, consistant with
# its name in the gridlabd/Taxonomy_Feeders repository.
GRIDLABD_FNAME = 'TopoCenter-PP_base.glm'

# Start and end days for the simulation
BEGIN_MONTH = 1
BEGIN_DAY = 1
END_MONTH = 1
END_DAY = 31

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

gld = glm.load(f'input/{GRIDLABD_FNAME}')

# Add the 'connection' model to the GLM file. This module contains the 'helics_msg' object
# necessary for HELICS integration
gld['modules'].append(
    {
        'name': 'connection',
        'attributes': {}
    }
)

# Set the run period for GridLAB-D
gld['clock']['starttime'] = f'2000-{BEGIN_MONTH}-{BEGIN_DAY} 00:00:00'
gld['clock']['stoptime'] = f'2000-{END_MONTH}-{END_DAY} 00:00:00'

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
        gld_obj['attributes'].pop('limit')

# Delete the house output, as we have replaced the GridLAB-D houses with external EnergyPlus
# models.
gld['objects'] = [
    obj for obj in gld['objects']
    if (obj['name'] != 'multi_recorder') or (obj['attributes']['file'] != 'House_log.csv')
]

# Hard-code bldg_hvac_operation_sch to 1 all the time
for fname in os.listdir('input/schedules'):
    df = pd.read_csv(f'input/schedules/{fname}', index_col = 0)
    df['bldg_hvac_operation_sch'] = 1
    df.to_csv(f'energyplus/schedules/{fname}')


house = [load['name'] for load in triplex_loads]
for fname in os.listdir('input/idf'):
    case = fname.replace('.idf','')

    # Load IDF
    idf = IDF(f'input/idf/{case}.idf')

    # Set EnergyPlus run period
    run_period = [
        run_period for run_period in idf.idfobjects['RUNPERIOD']
        if run_period['Name'] == 'Run Period 1'
    ]
    run_period = run_period[0] if len(run_period) == 1 else None
    run_period['Begin_Month'] = BEGIN_MONTH
    run_period['Begin_Day_of_Month'] = BEGIN_DAY
    run_period['End_Month'] = END_MONTH
    run_period['End_Day_of_Month'] = END_DAY

    # Point SCHEDULE:FILE objects to schedule CSVs
    for schedule in idf.idfobjects['SCHEDULE:FILE']:
        PATH = f'schedules/{case}_schedules.csv'
        schedule['File_Name'] = (
            PATH if PATH in schedule['File_Name'] else schedule['File_Name']
        )

    # Create new SCHEDULE:CONSTANT objects for the heating and cooling setpoints. These will be
    # actuated by the EnergyPlus Python API. 22.22 Celsius will be our default value.
    cooling_setpoint = idf.newidfobject('SCHEDULE:CONSTANT')
    heating_setpoint = idf.newidfobject('SCHEDULE:CONSTANT')
    cooling_setpoint['Name'] = 'cooling_setpoint'
    cooling_setpoint['Schedule_Type_Limits_Name'] = 'Any Number'
    cooling_setpoint['Hourly_Value'] = 22.22
    heating_setpoint['Name'] = 'heating_setpoint'
    heating_setpoint['Schedule_Type_Limits_Name'] = 'Any Number'
    heating_setpoint['Hourly_Value'] = 22.22

    # Point the DUALSETPOINT object to the SCHEDULE:CONSTANT objects
    setpoint = idf.idfobjects['THERMOSTATSETPOINT:DUALSETPOINT']
    setpoint = setpoint[0] if len(setpoint) == 1 else None
    setpoint['Heating_Setpoint_Temperature_Schedule_Name'] = 'heating_setpoint'
    setpoint['Cooling_Setpoint_Temperature_Schedule_Name'] = 'cooling_setpoint'

    # Save modified IDF
    idf.saveas(f'energyplus/idf/{fname}')

    # Create the building HELICS federate configuration file
    building_config['name'] = case
    with open(f'energyplus/helics_config/{case}.json', 'w', encoding='utf-8') as file:
        json.dump(building_config, file, indent=4)

    # Add the building subscription to the secondary HELICS configuration file
    info['object'] = house.pop(0)
    subscription['key'] = f'{case}/electricity_consumption'
    subscription['info'] = json.dumps(info)
    secondary['subscriptions'].append(subscription.copy())

    # Add the building federate to the HELICS CLI configuration file
    federate['exec'] = f'python ../building.py {case}'
    federate['name'] = case
    run['federates'].append(federate.copy())

# Create the secondary GLM file, secondary HELICS configuration file, and HELICS CLI
# configuration file
with open(f'gridlab-d/{GRIDLABD_FNAME}', 'w', encoding='utf-8') as file:
    file.write(glm.dumps(gld).replace('"', "'", 4))

with open('gridlab-d/secondary.json', 'w', encoding='utf-8') as file:
    json.dump(secondary, file, indent=4)

with open('helics/run.json', 'w', encoding='utf-8') as file:
    json.dump(run, file, indent=4)
