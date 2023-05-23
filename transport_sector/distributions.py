from scipy import stats
#from fitter import Fitter
from distfit import distfit
import numpy as np
import pandas as pd
import os
import matplotlib.pyplot as plt

def test():

    # data = stats.gamma.rvs(2, loc=1.5, scale=2, size=10000)
    # f = Fitter(data)
    # f.fit()
    # print(f.summary())
    X = np.random.normal(10, 3, 2000)
    # Initialize
    dist = distfit(todf=True)

    # Search for best theoretical fit on your empirical data
    results = dist.fit_transform(X)

    return None


class EVData:

    def __init__(
             self,
             csv_file,
             model_dir="saved_dist",
             upper_avg_speed=60
    ):
        """Method to generate distributions


        """
        self.csv_file = csv_file
        self.model_dir = model_dir
        self.mileage_by_cartype = [107,105,289,40]
        self.upper_avg_spped = upper_avg_speed

        if  not os.path.exists(self.model_dir):
            os.makedirs(self.model_dir)

        self.df, self.mileage, self.start_time, self.duration, self.car_type, self.houseid = self.get_deta()
        self.add_trip_frequency()

    def fit(self, save_model=False):
        #fist get the number of trips
        self.TripDist = self.get_number_of_trips()
        self.HouseDist = self.get_car_per_house_dist()
        self.StartTimeDist, self.CarTypeDist = self.get_ind_distribution(save_model=save_model)
        self.list_of_DurationDist, self.list_of_MileageDist, _, _ = self.get_dep_distribution(save_model=save_model)

        return None

    def inference(
            self,
            number_of_samples=10,
            load_model=False,
            max_iter=50,
            number_of_houses=None
    ):
        #loading all distribution objects
        if load_model:
            self.TripDist = self.get_number_of_trips()
            self.HouseDist = self.get_car_per_house_dist()
            self.StartTimeDist, self.CarTypeDist = self.get_ind_distribution(load_model=True)
            self.list_of_DurationDist, self.list_of_MileageDist, duration_names, mileage_names  = self.get_dep_distribution(load_model=True)

        assert hasattr(self, "TripDist")
        assert hasattr(self, "StartTimeDist")
        assert hasattr(self, "HouseDist")
        assert hasattr(self, "CarTypeDist")
        assert hasattr(self, "list_of_DurationDist")
        assert hasattr(self, "list_of_MileageDist")

        #first infer the number of cars per house
        if number_of_houses is not None:
            cars_per_house = self.HouseDist.sample(N=number_of_houses)
            cummulative_cars = np.cumsum(cars_per_house)
            # print(f"cars per house: {cars_per_house}")
            # print(f"Cars per house: {cummulative_cars}")

            #overwrite number of samples if number of cars is provided
        else:
            cars_per_house = None

        number_of_samples = np.sum(cars_per_house) if cars_per_house is not None else number_of_samples

        #first infer the number of cars per house
        #now that wee have loaded all the modules, we can start generating the
        number_of_trips = self.TripDist.sample(N=number_of_samples)
        number_of_cartypes = self.CarTypeDist.sample(N=number_of_samples)

        if number_of_houses is not None:
            house_id = np.zeros_like(number_of_trips)
            for i in range(number_of_houses):
                start_idx = 0 if i == 0 else cummulative_cars[i-1]
                house_id[start_idx: cummulative_cars[i]] = i + 1

        print(f"house id: {house_id}")
        print(f"Number of samples: ")
        df_list = [] #initialize empty ddataframe
        carid = 0
        #add missed tries
        #check inference for start times
        for n_car, (n_trips, ct) in enumerate(zip(number_of_trips, number_of_cartypes)):
            #include
            _check_bool = False
            _st_bool = False
            _dur_bool = False
            _mil_bool = False
            #TODO: Create end_times
            for iter in range(max_iter):
                start_times = self.StartTimeDist.sample(N=n_trips) #generte start times equal to the number of trips
                if np.all(start_times) > 0 and np.all(start_times) <24:
                    _st_bool = True
                    break
            #rearrange array in ascenting order
            start_times.sort()
            print(f"start_times: {start_times}")
            durations = np.zeros_like(start_times)
            mileages = np.zeros_like(start_times)
            carid += 1
            for n in range(n_trips):
                idx = ct - 1 #index to locate the duration and milage objs
                DurationDist = self.list_of_DurationDist[idx]
                MileageDist = self.list_of_MileageDist[idx]
                #decide on the upper and lower bounds when sampling
                min_val = 0 if n == 0 else start_times[n]
                max_val = 24 if n == n_trips - 1 else start_times[n+1]
                dur = -0.001 #assign duration to be a negative value
                mil = -0.001
                #asssign duration based on the sample
                for iter in range(max_iter):
                #while (start_times[n] + dur <=  min_val) or (start_times[n] + dur >= max_val) or dur < 0:
                    dur = DurationDist.sample()[0]
                    print(f"dur: {dur}")
                    if (start_times[n] + dur > min_val) and (start_times[n] + dur < max_val) and dur > 0:
                        _dur_bool = True
                        break

                #while mil <= 0:
                for iter in range(max_iter):
                    mil = MileageDist.sample()[0]
                    print(f"mil: {mil}")
                    if mil > 0 and (mil/dur) < self.upper_avg_spped:
                        durations[n] = dur
                        mileages[n] = mil
                        _mil_bool = True
                        break

            print(f"start times: {start_times}")
            print(f"durations: {durations}")
            print(f"mileages: {mileages}")

            #assert _st_bool and _mil_bool and _dur_bool

            ###Troubleshoot
            ctype = ct*np.ones_like(start_times)
            carid_arr = carid*np.ones_like(start_times)

            #Export data to pd dataframe
            df = pd.DataFrame()
            df["carid"] = carid_arr
            df["cartype"] = ctype
            df["start_times"] = start_times
            df["duration"] = durations
            df["end_time"] = durations + start_times
            df["mileages"] = mileages

            #adding house_id to the dataframe
            if number_of_houses is not None:
                df["house_id"] = house_id[n_car]*np.ones_like(start_times)


            #add in the

            df_list.append(df)

        df_out = (pd.concat(df_list)).reset_index(drop=True)
        return df_out

    def add_trip_frequency(self):
        """Method to add nunber of occurencces for each car id


        """
        self.df['trip_count'] = self.df.groupby('carid')['carid'].transform('count')
        self.df['trip_cumcount']  = self.df.groupby('carid').cumcount() + 1
        return None


    def get_deta(self):
        """Method to get both dependednt and independent variables

        """
        df = pd.read_csv(self.csv_file)
        mileage = df.loc[:, "mileage"]
        start_time = df.loc[:, "start"]
        end_time = df.loc[:, "end"]
        duration = end_time - start_time
        df["duration"] = duration
        cartype = df.loc[:, "cartype"]
        houseid = df.loc[:, "houseid"]
        return df, mileage, start_time, duration , cartype, houseid

    def get_number_of_trips(self):
        """Method to get the number of trips foe each cardi


        """
        trip_group = self.df.groupby("carid")["start"].nunique()
        trips = trip_group.values #get unique trips for each car id

        #call distribution function
        TripDist = Distribution(X=trips, type="categorical")
        TripDist.fit()

        return TripDist

    def get_car_per_house_dist(self):

        """
        method to add number of cars per house
        """
        unique_houseid = np.unique(self.houseid.values)
        number_of_cars = np.zeros_like(unique_houseid)

        for i, hid in enumerate(unique_houseid):
            df_s = self.df.loc[self.df["houseid"] == hid]
            #get the number of cars by house
            unique_cars = np.unique(df_s.loc[:, "carid"].values)
            number_of_cars[i] = len(unique_cars)

        #fit number of cars by houseid
        HouseDist = Distribution(X=number_of_cars, type="categorical")
        HouseDist.fit()

        return HouseDist


    def get_ind_distribution(self, load_model=False, save_model=True):
        """
        method to get distributions for independent variables

        """
        #fit continuous
        StartTimeDist = Distribution(X=self.start_time, type="cont")
        StartTimeDist.fit(dist_type="lognorm")

        if save_model:
            StartTimeDist.dist.save(os.path.join(self.model_dir, "StartTimeDist.pkl"))

        if load_model:
            path_to_file = os.path.join(self.model_dir, "StartTimeDist.pkl")
            assert os.path.exists(path_to_file)
            dist = distfit()
            dist.load(path_to_file)
            StartTimeDist.dist = dist

        ##fit cartype
        CartypeDist = Distribution(X=self.car_type, type="categorical")
        CartypeDist.fit()

        return StartTimeDist, CartypeDist

    def get_rest_period(self):

        """Get a new distribution for rest period

        """
        trip_group = self.df.groupby("carid")["start"].nunique()
        #print(trip_group)

        return None

    def get_dep_distribution(self, load_model=False, save_model=False):
        """
        method to fit duration and mileage distributions
        """
        #assume that duration and the mileage are dependent on the cartype
        unique_cartpe = np.unique(self.car_type)
        unique_trips = np.unique(self.df["trip_count"].values)
        #print(f"Unique: {unique_cartpe}")
        list_of_DurationDist = []
        list_of_MileageDist = []
        list_of_duration_names = []
        list_of_mileage_names = []

        for ct in unique_cartpe:
            #for n_trip in unique_trips:
                #specifying filenames
            duration_pkl = os.path.join(self.model_dir, f"duration_ct_{ct}.pkl")
            mileage_pkl = os.path.join(self.model_dir, f"mileage_ct_{ct}.pkl")
            list_of_duration_names.append(duration_pkl)
            list_of_mileage_names.append(mileage_pkl)

            df_s = self.df.loc[self.df["cartype"] == ct]
            duration = (df_s.loc[:, "end"] - df_s.loc[:, "start"]).values
            DurationDist = Distribution(X=duration, type="cont")
            mileage = df_s.loc[:, "mileage"].values
            MileageDist = Distribution(X=mileage, type="cont")

            #load model
            if load_model:
                #load distributions for duration and mileage
                dist = distfit()
                dist.load(duration_pkl)
                DurationDist.dist = dist

                dist = distfit()
                dist.load(mileage_pkl)
                MileageDist.dist = dist
            else:
                #distribution
                DurationDist.fit()
                MileageDist.fit()

                if save_model:
                    DurationDist.dist.save(duration_pkl)
                    MileageDist.dist.save(mileage_pkl)

            #append objects to list
            list_of_DurationDist.append(DurationDist)
            list_of_MileageDist.append(MileageDist)

        return list_of_DurationDist, list_of_MileageDist, list_of_duration_names, list_of_mileage_names


class Distribution:
    def __init__(self, X, type="cont"):
        """Class to fit distributions and fit distributions
        :param X (np.array): no.array (n, ) for the variable to fit
        :param type (str):

        """
        self.X  = X
        self.type = type

        assert self.type in ["cont", "continuous", "categorical"]


    def fit(self, dist_type=None):

        if self.type == "categorical":
            self.cum_prob, self.prob = self.categorical_fit()
        else:
            self.cum_prob = None
            self.dist = self.cont_fit(dist_type=dist_type)
            print(f"best distribution: {self.dist.model}")

        return None

    def cont_fit(self, dist_type=None):
        # Initialize
        if dist_type is None:
            dist = distfit(todf=True)
        else:
            dist = distfit(distr=[dist_type])

        # Search for best theoretical fit on your empirical data
        dist.fit_transform(self.X)

        return dist

    def categorical_fit(self):

        """
        method to generate categorical samples

        :return
        """
        X_u, counts = np.unique(self.X, return_counts=True) #number of unique data points
        probabiltiies = counts/np.sum(counts)
        cum_prob = np.cumsum(probabiltiies, axis=-1)  # shape (n1, n2, m)

        return cum_prob, probabiltiies

    @staticmethod
    def softmax(x):
        """Compute softmax values for each sets of scores in x."""
        e_x = np.exp(x - np.max(x))
        return e_x / e_x.sum()

    def sample(self, N=1):

        """Method to generate samples


        """
        if self.type == "categorical":
            samples = [self.categorical_inference() for n in range(N)]
        else:
            assert hasattr(self, "dist") #check that the distribution exists
            samples = self.dist.generate(n=N)

        return samples

    def categorical_inference(self):
        """
        Generate sample based on probabilties

        """
        r = np.random.uniform(size=(len(self.prob),))
        samples = np.argmax(self.cum_prob > r, axis=-1) + 1
        return samples



class Plotter:

    def __init__(
            self,
            df,
            output_dir="figures",
            vars=["cartype", "start_times", "duration", "end_time", "mileages"]
    ):

        self.df = df
        self.output_dir = output_dir
        self.vars = vars
        self.cartypes = [1, 2, 3, 4]

        if not os.path.exists(os.path.join(self.output_dir, "histogram")):
            os.makedirs(os.path.join(self.output_dir, "histogram"))

    def hist_cars_per_house(self, filename="cars_per_house.svg"):
        houseids = np.unique(self.df["house_id"].values)
        unique_cars_per_house = []
        for hid in houseids:
            df_s = self.df.loc[self.df["house_id"]==hid]
            ucars = np.unique(df_s["carid"].values)
            unique_cars_per_house.append(len(ucars))

        print(f"unique cars per house: {unique_cars_per_house}")
        return None

    def hist_trips_per_car(self, filename="trips_per_house.svg"):
        car_ids = np.unique(self.df["carid"].values)
        trips_per_car = []
        cartype_per_car = []
        for cid in car_ids:
            df_s = self.df.loc[self.df["carid"]==cid]
            ctype = df_s["cartype"].values[0]
            n_trips = len(df_s)
            trips_per_car.append(n_trips)
            cartype_per_car.append(ctype)
        f1 = os.path.join(self.output_dir, "histogram", filename)
        f2 = os.path.join(self.output_dir, "histogram", "hist_ctype.svg")
        self.plot_historgram(
            dist=trips_per_car,
            n_bins=4,
            filename=f1
        )

        self.plot_historgram(
            dist=cartype_per_car,
            n_bins=4,
            filename=f2
        )
        # print(f"unique trips per car: {np.unique(np.unique(trips_per_car))}")
        # print(f"cartype per car: {np.unique(cartype_per_car)}")
        return None

    def hist_start_times(self):

        """
        Method to plot histogram
        """
        start_times = self.df["start_times"].values
        filename = os.path.join(self.output_dir, "histogram", "hist_start_times.svg")
        self.plot_historgram(
            dist=start_times,
            n_bins=24,
            filename=filename,
            xlim=[0, 24]
        )


        return None

    def hist_dependent(self):
        """
        Method to plot the dependent variables
        """
        for ctype in self.cartypes:
            df_s = self.df.loc[self.df["cartype"]==ctype]
            mileages = df_s["mileages"].values
            duration = df_s["duration"].values
            self.plot_historgram(
                dist=mileages,
                n_bins=50,
                filename=os.path.join(self.output_dir, "histogram", f"mileages_ctype_{ctype}.svg"),
                xlim=[0, 150]
            )

            self.plot_historgram(
                dist=duration,
                n_bins=50,
                filename=os.path.join(self.output_dir, "histogram", f"duration_ctype_{ctype}.svg"),
                xlim=[0, 24]
            )



        return None

    def plot_historgram(
            self,
            dist,
            n_bins,
            xlabel=None,
            xlim=None,
            filename="test.svg"
    ):

        fig, axs = plt.subplots(1, 1, tight_layout=True)
        #N, bins, patches = axs.hist(dist, bins=n_bins)
        axs.hist(dist, bins=n_bins, density=True)
        if xlim is not None:
            plt.xlim(xlim)
        #axs[1].yaxis.set_major_formatter(PercentFormatter(xmax=1))
        plt.ylabel("PDF")
        plt.savefig(filename)
        plt.close()
        return None

if __name__ == "__main__":
    csv_file = "./data/trips.csv"
    SampeleData = EVData(csv_file=csv_file)
    #fit model
    #SampeleData.fit(save_model=True)
    #perform inference
    df_sample = SampeleData.inference(load_model=True, number_of_samples=10, number_of_houses=1000)

    print(f"TripDist")
    print(SampeleData.TripDist.summary)
    print(f"StartTimeDist: ")
    print(SampeleData.StartTimeDist.summary)
    print(f"House Dist")
    print(SampeleData.HouseDist.summary)
    print(f"list of Duration: ")
    print(SampeleData.list_of_DurationDist[0].summary)
    print(f"list of milagees: ")
    print(SampeleData.list_of_MileageDist[0].summary)

    # df_sample.to_csv("test.csv")
    #df_sample = pd.read_csv("test.csv")
    #print(df_sample)

    # TestPlot = Plotter(df=df_sample)
    # TestPlot.hist_cars_per_house()
    # TestPlot.hist_trips_per_car()
    # TestPlot.hist_start_times()
    # TestPlot.hist_dependent()
