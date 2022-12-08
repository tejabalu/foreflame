#!/usr/bin/env python
# coding: utf-8

# In[36]:


import csv
import io
import logging
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import date, timedelta

# Not used directly, but used via xarray
# import ecmwflibs
import cfgrib

# import cartopy.crs as ccrs
# import cartopy.feature as cfeature
import pandas as pd
import requests
import schedule
import xarray as xr

# In[37]:


class GFS:
    blob_container = "https://noaagfs.blob.core.windows.net/gfs"
    # WA boundary
    max_lat, min_lat = 49.25, 45.25
    max_long, min_long = -116.5, -125

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

        for i in range(len(self.forecast_hour)):
            self.setRequestUrl(i)
            self.fetchIdxFile()
        self.exportToCsv()

    def setRequestUrl(self, i):
        self.file_path = f"gfs.t{self.cycle:02}z.{self.product}.{self.resolution}.f{self.forecast_hour[i]}"
        self.url = f"{self.blob_container}/gfs.{self.dates}/{self.cycle:02}/{self.category}/{self.file_path}"
        # print(self.url)

    def fetchIdxFile(self):
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

        self.processData(ds)

    def processData(self, ds):
        # df, rslt
        df = ds.to_dataframe()

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

        # modify time format
        rslt["time"] = (
            rslt["time"]
            .astype(str)
            .apply(
                lambda x: str(
                    x.split()[0].split("-")[0]
                    + x.split()[0].split("-")[1]
                    + x.split()[0].split("-")[2]
                )
            )
        )
        # modify step format
        rslt["step"] = (
            rslt["step"].astype(str).apply(lambda x: x.split()[2].split(":")[0])
        )

        if self.data_type_str == "temp":
            rslt.drop(["surface", "valid_time"], axis=1, inplace=True)
            rslt["t"] = (rslt["t"] - 273.15) * 9 // 5 + 32  # convert to F
        elif self.data_type_str == "wind_speed":
            rslt.drop(["surface", "valid_time"], axis=1, inplace=True)

        elif self.data_type_str == "precipitation":
            rslt.drop(["surface", "valid_time"], axis=1, inplace=True)

        elif self.data_type_str == "soil_moisture":
            rslt.drop(["depthBelowLandLayer", "valid_time"], axis=1, inplace=True)
            rslt["soill"] = rslt["soill"] * 100
        self.output = self.output.append(rslt)

    def exportToCsv(self):
        self.output.to_csv(self.data_type_str + "_" + str(date.today()) + "_today.csv")
        logging.debug("export the {0} file to csv".format(self.data_type_str))


# In[38]:


def main():

    # create log file
    logging.basicConfig(
        filename=str(date.today()) + "_weathertoday_log.txt", level=logging.DEBUG
    )
    logging.debug("weather today schedule starting...")

    product = "pgrb2"
    resolution = "0p25"  # change to 0p25 later to get forecast for every hour
    cycle = 0  # model cycle runtime (i.e. 00, 06, 12, 18)

    category = "atmos"

    # data_type = [":TMP:surface", ":RH:entire atmosphere (considered as a single layer)",":GUST:surface"] # temperature # humid # wind speed
    data_type = [
        ":TMP:surface",
        ":GUST:surface",
        "APCP",
        "SOILL",
    ]  # temp: k, wind: m/s, precipitation: kg/m^2, soil moisture: proportion(*10^-3) -> kg/m^2
    data_type_str = ["temp", "wind_speed", "precipitation", "soil_moisture"]

    # substrace one day (***)
    date_ary = str(date.today()).split("-")
    today = date_ary[0] + date_ary[1] + date_ary[2]
    forecast_hour = ["003", "006", "009", "012", "015", "018", "021"]
    logging.debug("Today:{0}".format(today))

    for i in range(len(data_type_str)):
        logging.debug("day{0}".format(str(i)))
        # output: 10 days data with temperature, humidity, precipitation
        GFS(
            product,
            resolution,
            cycle,
            forecast_hour,
            category,
            today,
            data_type[i],
            data_type_str[i],
        )

    # read file and combine them together
    logging.debug("Read weather data file to combine them")
    temp = pd.read_csv(data_type_str[0] + "_" + str(date.today()) + "_today.csv")
    wind_speed = pd.read_csv(data_type_str[1] + "_" + str(date.today()) + "_today.csv")
    precipitation = pd.read_csv(
        data_type_str[2] + "_" + str(date.today()) + "_today.csv"
    )
    soil_moisture = pd.read_csv(
        data_type_str[3] + "_" + str(date.today()) + "_today.csv"
    )

    # copy lat and long and time from the source data
    data_all = pd.DataFrame(
        {
            "latitude": temp["latitude"],
            "longitude": temp["longitude"],
            "time": temp["time"],
            "step": temp["step"],
            "temp": temp["t"],
            "wind_speed": wind_speed["gust"],
            "precipitation": precipitation["tp"],
            "soil_moisture": soil_moisture["soill"],
        }
    )

    # mapping
    logging.debug("Read the position file ...")
    pixel_pos = pd.read_csv("pixel_coordinates.csv")  # lat, long
    logging.debug("Read the position file successfully")

    point_cnt = pixel_pos.shape[0]
    pos = pixel_pos.to_dict()
    mapping_dict = []  # defaultdict(dict)

    for i in range(point_cnt):
        # mapping lat and long to 0.25 resolution
        lat = pos["lat"][i]
        long = pos["long"][i]

        mapping_temp_dict = defaultdict(dict)
        mapping_temp_dict["latitude"] = lat
        mapping_temp_dict["longitude"] = long

        # base on time , lat, long filter out the data

        for j in forecast_hour:
            d = data_all[
                (data_all["time"] == int(today))
                & (data_all["step"] == int(j))
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
                column_name = s + "_" + j
                mapping_temp_dict[column_name] = d[s].mean()

        mapping_dict.append(mapping_temp_dict)

    # output to csv file
    logging.debug("writing the final result to csv")
    item_names = mapping_dict[0].keys()
    with open(
        "/home/tejabalu/www/flaskapp/static/" + today + "_todayweather" + ".csv", "w"
    ) as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=list(item_names))
        writer.writeheader()
        writer.writerows(mapping_dict)
    logging.debug("write the final result to csv successfully")

    # delete files
    for i in range(4):
        os.remove(data_type_str[i] + "_" + str(date.today()) + "_today.csv")
    logging.debug("delete file successfully")


if __name__ == "__main__":
    main()


# In[ ]:

