import pandas as pd

# Based on start_day and number_of_days_in_one_year, calculate if days are the peak/offpeak season and 
# weekday/weekend
#
# start_day: the assumption of day in Jan 1 [Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday]
#  number_of_days_in_one_year: [365, 366]
def day_calculation(start_day, number_of_days_in_one_year):
    day_list = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    month_day = {'Jan': 31,
                 'Feb': 28,
                 'Mar': 31,
                 'Apr': 30,
                 'May': 31,
                 'Jun': 30,
                 'Jul': 31,
                 'Aug': 31,
                 'Sep': 30,
                 'Oct': 31,
                 'Nov': 30,
                 'Dec': 31}
    if number_of_days_in_one_year == 366:
        month_day['Feb'] = 29
    # Identify the index in the day_list for start_day
    day_index = day_list.index(start_day)
    month_day_rec = []# month-day
    day_rec = []# Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, or Sunday
    season_day_rec = []# peak_wkdy, peak_wknd, offpeak_wkdy, offpeak_wknd
    for key in month_day:
        for i in range(month_day[key]):
            month_day_rec.append(key + '-' + str(i+1))
            day_rec.append(day_list[day_index])
            if key in ['May', 'Jun', 'Jul', 'Aug', 'Sep']:
                if day_index == 5 or day_index == 6:
                    season_day_rec.append('peak_wknd')
                else:
                    season_day_rec.append('peak_wkdy')
            else:
                if day_index == 5 or day_index == 6:
                    season_day_rec.append('offpeak_wknd')
                else:
                    season_day_rec.append('offpeak_wkdy')
            if day_index == 6:
                day_index = 0
            else:
                day_index += 1
    return month_day_rec, day_rec, season_day_rec
    
# Step 1: Use EPRI to calculate estimated annual energy consumption for a single industry facility.
# Step 2: Use Nw Council power demand to calculate annual energy consumption for the NW industry sector.
# Step 3: Based on the outputs of Steps 1 and 2, calculate the number of industry facilities in the NW.
# Step 4: Based on the load profiles for individual industry facilities in EPRI and number of industry 
# facilities, calculate the estimated aggregated load profile for the industry sector in the NW.
#
# start_day: the assumption of day in Jan 1 [Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday]
# number_of_days_in_one_year: [365, 366]
# output_path: the path of output csv file
def num_industry_estimation(start_day, number_of_days_in_one_year, output_path):
    # Step 1:
    # Get hourly load profiles from EPRI.csv
    # EPRI.csv was generated based on EPRI End Use: https://loadshape.epri.com/enduse
    load_profile_single_industry = pd.read_csv('../input_data/industry/EPRI.csv')
    # Other ("All Regions" only) is not considered in the industry sector in the EPRI
    end_uses = ['HVAC', 'Lighting', 'Machine Drives', 'Process Heating']
    # Peak season and off peak season's average weekday and weekend are used in this study
    # Peak weekday data is not used
    # This dictionary: {season_day: number of days}
    # Based on the description of EPRI: peak season: months of May through September; off-peak
    # season: months of October through April
    # In this estimation, we make the following assumptions:
    # - Number of days for each month is even (365/12)
    # - The ratio of weekday and weekend is 5:2
    # The value under each key is calculated by total days in one year/total months in one year
    # *number of months under a certain season*number of days in one week/total days in one week
    seasons_days = {'Peak Season, Average Weekday': 365.0/12.0*5.0*5.0/7.0,
                    'Peak Season, Average Weekend': 365.0/12.0*5.0*2.0/7.0,
                    'Off Peak Season, Average Weekday': 365.0/12.0*7.0*5.0/7.0,
                    'Off Peak Season, Average Weekend': 365.0/12.0*7.0*2.0/7.0}
    # Calculate the annual energy consumption for a single industry facility
    annual_energy_consumption_single_industry = 0
    for end_use in end_uses:
        for key_season_day in seasons_days:
            for i in range(len(load_profile_single_industry)):
                if load_profile_single_industry['End Use'][i] == end_use and load_profile_single_industry['Season/Day'][i] == key_season_day:
                    nominal_value = load_profile_single_industry['Nominal Value'][i]
                    for hour in range(1,25):
                        annual_energy_consumption_single_industry += nominal_value * load_profile_single_industry[str(hour)][i] * seasons_days[key_season_day] / 1000.0 # Unit: MWh
                    break
    
    # Step 2:
    # Get aMW (Average MW) from NW_Council_aMW.csv
    # NW_Council_aMW.csv was obtained from NW Council Industrial Sector Energy Use Forecasts: 
    # https://www.nwcouncil.org/2021powerplan_industrial-sector-energy-use-forecasts/
    # 2021powerplan_DemandData.xlsx
    # All Industrial tab
    amw_nw_industry_sector = pd.read_csv('../input_data/industry/NW_Council_aMW.csv')
    # This research selects BaseCase scenario 2019 to calculate annual energy consumption for the NW industry sector
    for i in range(len(amw_nw_industry_sector)):
        if 'Scenario Name: BaseCase' in amw_nw_industry_sector['Scenario'][i]:
            amw_total = amw_nw_industry_sector['2019'][i]
            break
    # Annual energy consumption for the NW industry sector = aMW * 365 (days) * 24 (hours)
    annual_energy_consumption_industry_sector = amw_total * 24.0 * 365.0
    
    # Step 3:
    # Number of industry facilities = annual_energy_consumption_industry_sector / annual_energy_consumption_single_industry
    number_industry_facilities = annual_energy_consumption_industry_sector / annual_energy_consumption_single_industry
    
    # Step 4:
    # Hourly load profiles from EPRI.csv * Number of industry facilities
    # Calculate end-use load profile for the NW industry sector
    # agg_load_profile:
    # First layer: end_uses = ['HVAC', 'Lighting', 'Machine Drives', 'Process Heating']
    # Second layer: seasons_days = ['Peak Season, Average Weekday', 'Peak Season, Average Weekend', 
    # 'Off Peak Season, Average Weekday', 'Off Peak Season, Average Weekend']
    # Third layer: hourly load profile
    agg_load_profile = []
    for end_use in end_uses:
        agg_load_profile_enduse = []
        for key_season_day in seasons_days:
            agg_load_profile_enduse_seasonday = []
            for i in range(len(load_profile_single_industry)):
                if load_profile_single_industry['End Use'][i] == end_use and load_profile_single_industry['Season/Day'][i] == key_season_day:
                    nominal_value = load_profile_single_industry['Nominal Value'][i]
                    for hour in range(1,25):
                        agg_load_profile_enduse_seasonday.append(nominal_value * load_profile_single_industry[str(hour)][i] / 1000.0 * number_industry_facilities) # Unit: MWh
                    break
            agg_load_profile_enduse.append(agg_load_profile_enduse_seasonday)
        agg_load_profile.append(agg_load_profile_enduse)
    
    # Store the result to csv file
    # Calculate if days are the peak/offpeak season and weekday/weekend
    month_day_rec, day_rec, season_day_rec = day_calculation(start_day, number_of_days_in_one_year)
    # Aggregated total and enduse load profiles
    agg_load_profile_total = []
    agg_load_profile_hvac = []
    agg_load_profile_lighting = []
    agg_load_profile_machine_drives = []
    agg_load_profile_process_heating = []
    for x in season_day_rec:
        if x == 'peak_wkdy':
            k = 0
        elif x == 'peak_wknd':
            k = 1
        if x == 'offpeak_wkdy':
            k = 2
        else:
            k = 3
        for i in range(24):
            agg_load_profile_total.append(agg_load_profile[0][k][i] + agg_load_profile[1][k][i] + agg_load_profile[2][k][i] + agg_load_profile[3][k][i])
            agg_load_profile_hvac.append(agg_load_profile[0][k][i])
            agg_load_profile_lighting.append(agg_load_profile[1][k][i])
            agg_load_profile_machine_drives.append(agg_load_profile[2][k][i])
            agg_load_profile_process_heating.append(agg_load_profile[3][k][i])
    # update month_day_rec, day_rec, season_day_rec, and add time information
    month_day_hr_rec = []
    day_hr_rec = []
    season_day_hr_rec = []
    time = []
    for i in range(number_of_days_in_one_year):
        for j in range(1,25):
            month_day_hr_rec.append(month_day_rec[i])
            day_hr_rec.append(day_rec[i])
            season_day_hr_rec.append(season_day_rec[i])
            time.append(j)
    df = pd.DataFrame()
    df['Month/Day'] = month_day_hr_rec
    df['Week_Day'] = day_hr_rec
    df['Season/Weekday'] = season_day_hr_rec
    df['Time'] = time
    df['Aggregated Total Load Profile [MWh]'] = agg_load_profile_total
    df['Aggregated HVAC Load Profile [MWh]'] = agg_load_profile_hvac
    df['Aggregated Lighting Load Profile [MWh]'] = agg_load_profile_lighting
    df['Aggregated Machine Drives Load Profile [MWh]'] = agg_load_profile_machine_drives
    df['Aggregated Process Heating Load Profile [MWh]'] = agg_load_profile_process_heating
    df.to_csv(output_path, index = False)
    
num_industry_estimation('Sunday', 365, '../output/output_industry.csv')
