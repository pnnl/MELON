'''
Produces processed input files from the unprocessed input files in input/
'''
import os
import json
import glm
from eppy.modeleditor import IDF

IDF.setiddname('input/Energy+V9_5_0.idd')

GRIDLABD_FNAME = 'TopoCenter-PP_base.glm'

BEGIN_MONTH = 1
BEGIN_DAY = 1
END_MONTH = 1
END_DAY = 31

SIM_DIRS = [
    'energyplus/idf',
    'energyplus/helics_config',
    'energyplus/output',
    'gridlab-d',
    'helics'
]

for directory in SIM_DIRS:
    if not os.path.exists(directory):
        os.makedirs(directory)

with open('input/building_config.json', encoding='utf-8') as file:
    building_config = json.load(file)

with open('input/secondary_feeder.json', encoding='utf-8') as file:
    secondary_feeder = json.load(file)

with open('input/subscription.json', encoding='utf-8') as file:
    subscription = json.load(file)
info = json.loads(subscription['info'])

with open('input/run.json', encoding='utf-8') as file:
    run = json.load(file)

with open('input/federate.json', encoding='utf-8') as file:
    federate = json.load(file)

gld = glm.load(f'input/{GRIDLABD_FNAME}')

gld['modules'].append(
    {
        'name': 'connection',
        'attributes': {}
    }
)

gld['clock']['starttime'] = f'2000-{BEGIN_MONTH}-{BEGIN_DAY} 00:00:00'
gld['clock']['stoptime'] = f'2000-{END_MONTH}-{END_DAY} 00:00:00'

gld['objects'].append(
    {
        'name': 'helics_msg',
        'attributes': {
            'name': 'secondary_feeder',
            'configure': 'secondary_feeder.json'
        },
        'children': []
    }
)

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

gld['objects'] = [
    obj for obj in gld['objects']
    if (obj['name'] != 'multi_recorder') or (obj['attributes']['file'] != 'House_log.csv')
]

house = [load['name'] for load in triplex_loads]
fnames = os.listdir('input/idf')
for fname in fnames:
    case = fname.replace('.idf','')
    idf = IDF(f'input/idf/{case}.idf')

    run_period = [
        run_period for run_period in idf.idfobjects['RUNPERIOD']
        if run_period['Name'] == 'Run Period 1'
    ]
    run_period = run_period[0] if len(run_period) == 1 else None
    run_period['Begin_Month'] = BEGIN_MONTH
    run_period['Begin_Day_of_Month'] = BEGIN_DAY
    run_period['End_Month'] = END_MONTH
    run_period['End_Day_of_Month'] = END_DAY

    for schedule in idf.idfobjects['SCHEDULE:FILE']:
        PATH = f'schedules/{case}_schedules.csv'
        schedule['File_Name'] = f'../input/{PATH}' if PATH in schedule['File_Name'] else schedule['File_Name']

    cooling_setpoint = idf.newidfobject('SCHEDULE:CONSTANT')
    heating_setpoint = idf.newidfobject('SCHEDULE:CONSTANT')
    cooling_setpoint['Name'] = 'cooling_setpoint'
    cooling_setpoint['Schedule_Type_Limits_Name'] = 'Any Number'
    cooling_setpoint['Hourly_Value'] = 22.22
    heating_setpoint['Name'] = 'heating_setpoint'
    heating_setpoint['Schedule_Type_Limits_Name'] = 'Any Number'
    heating_setpoint['Hourly_Value'] = 22.22

    setpoint = idf.idfobjects['THERMOSTATSETPOINT:DUALSETPOINT']
    setpoint = setpoint[0] if len(setpoint) == 1 else None
    setpoint['Heating_Setpoint_Temperature_Schedule_Name'] = 'heating_setpoint'
    setpoint['Cooling_Setpoint_Temperature_Schedule_Name'] = 'cooling_setpoint'

    idf.saveas(f'energyplus/idf/{fname}')

    building_config['name'] = case
    with open(f'energyplus/helics_config/{case}.json', 'w', encoding='utf-8') as file:
        json.dump(building_config, file, indent=4)

    info['object'] = house.pop(0)
    subscription['key'] = f'{case}/electricity_consumption'
    subscription['info'] = json.dumps(info)
    secondary_feeder['subscriptions'].append(subscription.copy())

    federate['exec'] = f'python ../building.py {case}'
    federate['name'] = case
    run['federates'].append(federate.copy())

with open(f'gridlab-d/{GRIDLABD_FNAME}', 'w', encoding='utf-8') as file:
    file.write(glm.dumps(gld).replace('"', "'", 4))

with open('gridlab-d/secondary_feeder.json', 'w', encoding='utf-8') as file:
    json.dump(secondary_feeder, file, indent=4)

with open('helics/run.json', 'w', encoding='utf-8') as file:
    json.dump(run, file, indent=4)
