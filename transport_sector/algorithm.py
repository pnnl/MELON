import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os

from distributions import EVData

class Algo:

    def __init__(
            self,
            trip_csv="./data/trips.csv",
            init_soc_min=0.15,
            init_soc_max=0.80,
            soc_threshold_min=0.10,
            soc_threshold_max=0.20,
            soc_upper_min=0.85,
            soc_upper_max=1.0,
            soc_max=0.90,
            charging_rate=3.3,
            profile_csv="./data/ChargingProfiles.csv",
            number_of_samples=10,
            public_speed_limit=25,
            avg_rt_speed=40,
            duration_limit=0.5,
            charging_eff=0.90,
            weekday=True,
            fig_dir="figures"
    ):
        """Class for computing the external algorithm


        """
        self.trip_csv = trip_csv
        self.init_soc_min = init_soc_min
        self.init_soc_max = init_soc_max
        self.soc_threshold_min = soc_threshold_min
        self.soc_threshold_max = soc_threshold_max
        self.soc_upper_min = soc_upper_min
        self.soc_upper_max = soc_upper_max
        self.soc_max = soc_max
        self.charging_rate = charging_rate
        self.profile_csv = profile_csv
        self.number_of_samples = number_of_samples
        self.public_speed_limit = public_speed_limit
        self.duration_limit = duration_limit
        self.avg_rt_speed = avg_rt_speed
        self.charging_eff = charging_eff
        self.weekday = weekday
        self.fig_dir = fig_dir

        self.mileage_by_cartype = [107, 105, 289, 40]
        self.kwh_by_cartype = [30, 24, 100, 23]
        self.df_prof, self.residence_weekday, self.residence_weekend, self.both_weekday, self.both_weekend = self.read_data()
        self.residence_weekday_diff, self.residence_weekend_diff = self.compute_diff()
        self.df_sample = self.get_sample_data()


    def read_data(self):
        df = pd.read_csv(self.profile_csv)
        residence_weekday = df.loc[:, "Residence Only - Weekday"].values
        residence_weekend = df.loc[:, "Residence Only - Weekend"].values
        both_weekday = df.loc[:, "Residence+Work Weekday"].values
        both_weekend =  df.loc[:, "Residence+Work Weekend"].values
        return df, residence_weekday, residence_weekend, both_weekday, both_weekend

    def compute_diff(self):
        res_weekday_diff = np.diff(self.residence_weekday) > 0
        res_weekend_diff = np.diff(self.residence_weekend) > 0
        return res_weekday_diff, res_weekend_diff

    def get_sample_data(
            self,
            load_model=True
    ):

        SampeleData = EVData(csv_file=self.trip_csv)
        if not load_model:
            SampeleData.fit(save_model=True)
        df = SampeleData.inference(load_model=load_model, number_of_samples=self.number_of_samples)
        return df

    def run(
        self,
        weekday=True
    ):
        """Method to run the algorithm

        """
        car_ids = np.unique(self.df_sample["carid"].values)
        #initialize the two sectors
        agg_transportation_profile = np.zeros(24)
        #Store the consumption information by car id

        res_energy_data = []
        res_schedule_data = []
        for id in car_ids:
            df_s = self.df_sample.loc[self.df_sample["carid"] == id]
            init_SOC = np.random.uniform(low=self.init_soc_min, high=self.init_soc_max)  # initial SOC
            #print(df_s.columns)
            start_times = df_s.loc[:, "carid"].values
            duration = df_s.loc[:, "duration"].values
            mileages = df_s.loc[:, "mileages"].values
            cartypes = df_s.loc[:, "cartype"].values

            #initialize array informtion
            homecharge_by_carid = None
            consumption_per_car = np.zeros(24)
            #print(f"start_times: {start_times}")
            for tr, st in enumerate(start_times):
                SOC = (init_SOC*self.mileage_by_cartype[int(cartypes[tr]) - 1] - mileages[tr])/self.mileage_by_cartype[int(cartypes[tr]) - 1]
                remaining_Mileage = SOC*self.mileage_by_cartype[int(cartypes[tr]) - 1]
                #stochastically compute the threshold limit
                soc_threshold = np.random.uniform(low=self.soc_threshold_min, high=self.soc_threshold_max)
                #initialize a temporary array
                #charging in public scenarios
                if (remaining_Mileage < mileages[tr]/2) and (mileages[tr]/duration[tr] < self.public_speed_limit and duration[tr] > self.duration_limit):
                    charge_time_start = round(start_times[tr] + 0.5*mileages[tr]/self.avg_rt_speed)
                    charge_time_start = charge_time_start - 24 if charge_time_start > 24 else charge_time_start
                    charge_start_idx = charge_time_start - 1 if charge_time_start > 0 else 0 #-1 because python indexing starts at 0
                    site_power, schedule = self.compute_energy_consumption(charge_start_idx, int(cartypes[tr])-1, soc_threshold, False)
                    agg_transportation_profile += schedule
                elif SOC < soc_threshold: #charging at home case
                    trip_end_time = st + duration[tr] #end time of the tri
                    trip_end_time = trip_end_time - 24 if trip_end_time > 24 else trip_end_time
                    end_time_idx = int(np.floor(trip_end_time)) - 1
                    #select profile based on weekday or a weekday or a weekend, compute the gradient
                    grad = self.residence_weekday_diff.copy() if weekday else self.residence_weekend_diff.copy()
                    #Get the gradient after the end time is complete
                    grad_from_idx = grad[end_time_idx:] if np.any(grad[end_time_idx:]) else grad
                    #Note from Aowanin: Incorporating stochasticity in start time
                    charge_time_start = np.where(grad_from_idx)[0][0] + end_time_idx if np.any(grad[end_time_idx:]) else np.where(grad_from_idx)[0][0]#select the first timestep
                    site_power, schedule = self.compute_energy_consumption(charge_time_start, int(cartypes[tr]) - 1,
                                                                           soc_threshold, False)
                    consumption_per_car += schedule
                    #homecharge_by_carid = schedule[:, None] if homecharge_by_carid is None else np.concat((homecharge_by_carid, schedule[:, None]), axis=1)
                    # print(f"homecharge by carid: ")
                    # print(homecharge_by_carid)
                    #plotting
                    #find the start time based on the existing NW Council profile
                else:
                    pass
            #collect the schedule and the site power data into a list
            home_schedule = (consumption_per_car > 0).astype(int)
            print(f"home schedule: {home_schedule}")
            res_energy_data.append()
            #plot by car
            if np.any(consumption_per_car) > 0:
                #print(f"consumption per car:  {consumption_per_car}")
                filename = f"schedule_car_{int(id)}.svg"
                self.plot(schedule=consumption_per_car, filename=filename)
        #print(f"agg_profile: {agg_transportation_profile}")
        self.plot(agg_transportation_profile)
        return None

    def compute_energy_consumption(
            self,
            charge_time_start,
            cartype_idx,
            soc_min,
            bldg_sch=True
    ):
        """
        Method to compute energy consumption at site

        """
        schedule = np.zeros(24)
        soc_max = np.random.uniform(low=self.soc_upper_max, high=self.soc_upper_min)
        site_power = self.kwh_by_cartype[cartype_idx]*self.charging_eff*(soc_max - soc_min)
        charge_duration = site_power/self.charging_rate
        charge_time_end = round(charge_time_start + charge_duration)
        charge_time_end = charge_time_end - 24 if charge_time_end > 24 else charge_time_end
        schedule[charge_time_start: charge_time_end] = site_power if not bldg_sch else 1
        return site_power, schedule

    def plot(
            self,
            schedule,
            filename="test.svg",
            xlabel="Time (Hours)",
            ylabel="Electricity Consumption (Kwh)"
    ):
        if not os.path.exists(self.fig_dir):
            os.makedirs(self.fig_dir)

        t = np.arange(schedule.shape[0])
        plt.plot(t, schedule, 'k-')
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.savefig(os.path.join(self.fig_dir, filename))
        plt.close()
        return None



if __name__ == "__main__":
    TestAlgo = Algo(number_of_samples=100)
    TestAlgo.run()
