#!/usr/bin/env python
# coding: utf-8

# In[1]:


import csv
import io
import logging
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import date, timedelta

# Not used directly, but used via xarray
import cfgrib

# import matplotlib.pyplot as plt
import pandas as pd
import requests
import xarray as xr

# import cartopy.crs as ccrs
# import cartopy.feature as cfeature


# In[2]:


class GFS:
    blob_container = "https://noaagfs.blob.core.windows.net/gfs"
    # WA boundary
    max_lat, min_lat = 49.00670390258853, 45.54247096392627
    max_long, min_long = -116.9281144867532, -124.73215572220116

    """
    output_temp = pd.DataFrame()
    output_humid = pd.DataFrame()
    output_windspeed = pd.DataFrame()   

    """
    """
    for i in range(predict_day):
        temp_date = date.today() + timedelta(days=i)
        date_ary.append(str(temp_date.strftime("%Y%m%d")))
    print('dates: {0}'.format(date_ary))
    """

    def __init__(
        self,
        product,
        resolution,
        cycle,
        forecast_hour,
        category,
        dates,
        data_type,
        data_type_str,
    ):
        self.product = product
        self.resolution = resolution
        self.cycle = cycle
        self.forecast_hour = forecast_hour
        self.category = category
        self.dates = dates
        self.data_type = data_type
        self.data_type_str = data_type_str
        self.file_path = ""
        self.url = ""
        self.output = pd.DataFrame()

        # today and the previous four days
        logging.debug("data period:{0}".format(self.dates))
        for i in range(1, len(dates)):  # exclude the first date(for handle exception)
            logging.debug("date{0}".format(str(i)))
            isPredict = False
            try:
                self.setRequestUrl(i, self.forecast_hour[0])
                self.fetchIdxFile(isPredict, 0)
            except:
                self.setRequestUrl(i - 1, self.forecast_hour[0] + 24 - 1)
                self.fetchIdxFile(isPredict, 0)
                logging.debug(
                    "[ERROR] cannot find the data on {0}".format(self.dates[i])
                )
        # the next five days
        logging.debug("prediction data period:{0}".format(self.forecast_hour[1:]))
        for i in range(1, len(forecast_hour)):
            logging.debug(forecast_hour[i])
            isPredict = True
            # need to change the date
            try:
                self.setRequestUrl(len(self.dates) - 1, self.forecast_hour[i])
                self.fetchIdxFile(isPredict, i)
            except:
                self.setRequestUrl(len(self.dates) - 2, self.forecast_hour[i] + 24 - 1)
                self.fetchIdxFile(isPredict, i)
                logging.debug(
                    "[ERROR] cannot find the data on {0}".format(self.dates[i])
                )
        self.exportToCsv()

    def setRequestUrl(self, i, forecast_h):
        self.file_path = (
            f"gfs.t{self.cycle:02}z.{self.product}.{self.resolution}.f{forecast_h:03}"
        )
        self.url = f"{self.blob_container}/gfs.{self.dates[i]}/{self.cycle:02}/{self.category}/{self.file_path}"
        # print(self.url)

    def fetchIdxFile(self, isPredict, day_after):
        # todo
        r = requests.get(f"{self.url}.idx")
        idx = r.text.splitlines()
        data_idx = [l for l in idx if self.data_type in l][0].split(":")
        # print("data line:", data_idx)
        line_num = int(data_idx[0])
        range_start = data_idx[1]
        next_line = idx[line_num].split(":") if line_num < len(idx) else None
        range_end = next_line[1] if next_line else None
        # print(f"Byte range: {range_start}-{range_end}")

        file = tempfile.NamedTemporaryFile(prefix="tmp_", delete=False)
        headers = {"Range": f"bytes={range_start}-{range_end}"}
        resp = requests.get(self.url, headers=headers, stream=True)

        with file as f:
            f.write(resp.content)

        ds = xr.open_dataset(
            file.name, engine="cfgrib", backend_kwargs={"indexpath": ""}
        )

        self.processData(ds, isPredict, day_after)

    def processData(self, ds, isPredict, day_after):
        # df, rslt
        df = ds.to_dataframe()
        # print(df)
        df.reset_index(inplace=True)

        # pull out lat
        rslt = df[(df["latitude"] <= self.max_lat) & (df["latitude"] >= self.min_lat)]
        # pusll out long (0-360)
        rslt = rslt[
            (rslt["longitude"] <= self.max_long + 180)
            & (rslt["longitude"] >= self.min_long + 180)
        ]

        # modify longitude
        rslt["longitude"] = rslt["longitude"] - 180

        # if the data is predict data, modify the date base on step
        if isPredict:
            rslt["time"] = rslt["time"] + timedelta(days=day_after)

        # modify time format
        rslt["time"] = (
            rslt["time"]
            .astype(str)
            .apply(
                lambda x: x.split()[0].split("-")[0]
                + x.split()[0].split("-")[1]
                + x.split()[0].split("-")[2]
            )
        )

        if self.data_type_str == "temp":
            rslt.drop(["step", "surface", "valid_time"], axis=1, inplace=True)

        elif self.data_type_str == "wind_speed":
            rslt.drop(["step", "surface", "valid_time"], axis=1, inplace=True)

        elif self.data_type_str == "precipitation":
            rslt.drop(["step", "surface", "valid_time"], axis=1, inplace=True)

        elif self.data_type_str == "soil_moisture":
            rslt.drop(
                ["step", "depthBelowLandLayer", "valid_time"], axis=1, inplace=True
            )
            rslt["soill"] = rslt["soill"] * 100
        # print(rslt)
        self.output = self.output.append(rslt)

    def exportToCsv(self):
        self.output.to_csv(self.data_type_str + "_" + str(date.today()) + ".csv")


# In[3]:


# filter datta has error
def main():

    # create log file
    logging.basicConfig(
        filename=str(date.today()) + "_weatherprediction_log.txt", level=logging.DEBUG
    )
    logging.debug("weather prediction schedule starting...")

    product = "pgrb2"
    resolution = "0p25"  # change to 0p25 later to get forecast for every hour
    cycle = 0  # model cycle runtime (i.e. 00, 06, 12, 18)
    category = "atmos"
    predict_day = 6

    # data_type = [":TMP:surface", ":RH:entire atmosphere (considered as a single layer)",":GUST:surface"] # temperature # humid # wind speed
    data_type = [
        ":TMP:surface",
        ":GUST:surface",
        "APCP",
        "SOILL",
    ]  # temp: k, wind: m/s, precipitation: kg/m^2, soil moisture: proportion(*10^-3) -> kg/m^2
    data_type_str = ["temp", "wind_speed", "precipitation", "soil_moisture"]

    date_ary = []
    period = []

    for i in range(predict_day):  # add one more day before in case the data lacking
        temp_date = date.today() - timedelta(days=predict_day - i - 1)
        date_ary.append(str(temp_date.strftime("%Y%m%d")))
    # print('dates: {0}'.format(date_ary))
    forecast_hour = [13, 37, 61, 85, 109, 133]  # 000 - 384

    # total weather period

    for i in range(11):
        # first day +
        temp = date.today() - timedelta(days=predict_day - 1) + timedelta(days=i)
        period.append(str(temp.strftime("%Y%m%d")))

    # print('period:{0}'.format(period))
    logging.debug(date.today())
    logging.debug(date_ary)
    logging.debug(period)
    logging.debug("finish date setting")
    logging.debug("start to grab data")
    for i in range(len(data_type_str)):
        logging.debug(data_type_str[i])
        # output: 10 days data with temperature, humidity, precipitation
        GFS(
            product,
            resolution,
            cycle,
            forecast_hour,
            category,
            date_ary,
            data_type[i],
            data_type_str[i],
        )
    logging.debug("finish grab data")
    logging.debug("read file and ccombine them together")

    # read file and combine them together
    temp = pd.read_csv(data_type_str[0] + "_" + str(date.today()) + ".csv")
    wind_speed = pd.read_csv(data_type_str[1] + "_" + str(date.today()) + ".csv")
    precipitation = pd.read_csv(data_type_str[2] + "_" + str(date.today()) + ".csv")
    soil_moisture = pd.read_csv(data_type_str[3] + "_" + str(date.today()) + ".csv")

    logging.debug("finish reading the data")

    logging.debug("start to process the data")

    # copy lat and long and time from the source data
    data_all = pd.DataFrame(
        {
            "latitude": temp["latitude"],
            "longitude": temp["longitude"],
            "time": temp["time"],
            "temp": temp["t"],
            "wind_speed": wind_speed["gust"],
            "precipitation": precipitation["tp"],
            "soil_moisture": soil_moisture["soill"],
        }
    )

    logging.debug("reading pixel coordinates file")

    # mapping
    pixel_pos = pd.read_csv("pixel_coordinates.csv")  # lat, long
    point_cnt = pixel_pos.shape[0]
    pos = pixel_pos.to_dict()
    mapping_dict = []  # defaultdict(dict)
    for i in range(point_cnt):
        # mapping lat and long to 0.25 resolution
        lat = pos["lat"][i]
        long = pos["long"][i]

        mapping_temp_dict = defaultdict(dict)
        mapping_temp_dict["id"] = i
        mapping_temp_dict["latitude"] = lat
        mapping_temp_dict["longitude"] = long

        for n, dd in enumerate(period):
            # base on time , lat, long filter out the data
            d = data_all[
                (data_all["time"] == int(dd))
                & (
                    (
                        (data_all["latitude"] > (lat - 0.125))
                        & (data_all["latitude"] < (lat + 0.125))
                        & (
                            (data_all["longitude"] > (long - 0.125))
                            & (data_all["longitude"] < (long + 0.125))
                        )
                    )
                )
            ]
            for s in data_type_str:
                column_name = s + str(n)
                mapping_temp_dict[column_name] = d[s].mean()

        mapping_dict.append(mapping_temp_dict)
    logging.debug("export the result in to csv ")
    # output to csv file
    item_names = mapping_dict[0].keys()
    with open(date_ary[-1] + "_predictweather" + ".csv", "w") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(item_names))
        writer.writeheader()
        writer.writerows(mapping_dict)

    # delete files
    for i in range(4):
        os.remove(data_type_str[i] + "_" + str(date.today()) + ".csv")
    logging.debug("delete file successfully")

    logging.debug("finish all the script")


if __name__ == "__main__":
    main()


# In[ ]:

