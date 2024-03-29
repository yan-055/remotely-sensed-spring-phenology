import arcpy, os, glob
import time
import csv
import re  ## for research
import decimal
import numpy as np
from osgeo import gdal, osr
from arcpy import env
from arcpy.sa import *
from scipy import stats
import gc
import pandas as pd


## open tiff file
def return_band(mcd12q1_file_name, band_number):
    # open mcd12q1
    fn_mcd12q1 = mcd12q1_file_name
    if band_number == 1:
        ds_mcd12q1 = gdal.Open(fn_mcd12q1)
    if ds_mcd12q1 is None:
        print "Could not open " + fn_mcd12q1
        exit(1)

    geoTransform = ds_mcd12q1.GetGeoTransform()
    proj = ds_mcd12q1.GetProjection()
    cols = ds_mcd12q1.RasterXSize
    rows = ds_mcd12q1.RasterYSize
    rasterband = ds_mcd12q1.GetRasterBand(band_number)
    band = np.array(rasterband.ReadAsArray())

    return band, geoTransform, proj, cols, rows

    ds_mcd12q1 = None
    band = None


## export the .tif file
def output_file(output_name, output_array, geoTransform, proj, cols, rows):
    format = "GTiff"
    driver = gdal.GetDriverByName(format)
    outDataset = driver.Create(output_name, cols, rows, 1, gdal.GDT_Int16)
    outBand = outDataset.GetRasterBand(1)
    outBand.WriteArray(output_array, 0, 0)
    outBand.FlushCache()
    outDataset.SetGeoTransform(geoTransform)
    outDataset.SetProjection(proj)


## removing the outlier of greenup metrics (2001-2016) at each pixel
def remove_outlier(pixel_in):
    df_in = pd.DataFrame(data=pixel_in, columns=['pixelIn'])
    q1 = df_in['pixelIn'].quantile(0.25)
    q3 = df_in['pixelIn'].quantile(0.75)
    iqr = q3 - q1  # Interquartile range
    fence_low = q1 - 1.5 * iqr
    fence_high = q3 + 1.5 * iqr
    df_out = df_in.loc[(df_in['pixelIn'] > fence_low) & (df_in['pixelIn'] < fence_high)]
    return list(df_out['pixelIn'])


## checking the order of year in greenup input list
def check_yearOrder(grenupList):
    outputValue = 0
    if (len(grenupList) == 16):

        yearList = []
        for each in grenupList:
            yearList.append(each.split("MCD12Q2.")[1][1:5])

        if (yearList[0] == '2001' and yearList[1] == '2002' and yearList[2] == '2003' and yearList[3] == '2004' and
                yearList[4] == '2005' and yearList[5] == '2006' and yearList[6] == '2007' and yearList[7] == '2008' and
                yearList[8] == '2009' and yearList[9] == '2010' and yearList[10] == '2011' and yearList[
                    11] == '2012' and
                yearList[12] == '2013' and yearList[13] == '2014' and yearList[14] == '2015' and yearList[
                    15] == '2016'):
            outputValue = 1

    return outputValue


## exporting the combined B1 and B2 results
def export_combinedStat(Year_Mean, MeanName, Year_Trend, TrendName, Year_pValue, pValueName,
                        Year_SD, SD_Name):
    arcpy.CopyRaster_management(Year_Mean, MeanName, "DEFAULTS", "", "32767", "", "", "16_BIT_SIGNED")
    arcpy.CopyRaster_management(Year_Trend, TrendName, "DEFAULTS", "", "32767", "", "", "32_BIT_FLOAT")
    arcpy.CopyRaster_management(Year_pValue, pValueName, "DEFAULTS", "", "32767", "", "", "16_BIT_SIGNED")
    arcpy.CopyRaster_management(Year_SD, SD_Name, "DEFAULTS", "", "32767", "", "", "32_BIT_FLOAT")


## making the statistics of greenup metrics (Band1, 2001-2016) at each pixel, including
## including coefficient of linear regression, p-value, mean, median and standard deviation
def CalB1_GreenupStat(greenupList, limitCount, trendName, pValueName, meanName, medName, sdName):
    band0, geoTransform0, proj0, cols0, rows0 = return_band(greenupList[0], 1)

    open("B1_TempP-Value.txt", "w").close()
    open("B1_TempMean.txt", "w").close()
    open("B1_TempMedian.txt", "w").close()
    open("B1_TempSD.txt", "w").close()

    for i in range(0, rows0):
        print i
        # print str(time.ctime())
        oneRowPixels = band0[i, :]
        pValueList = []
        meanList = []
        medList = []
        sdList = []
        for greenupFile in range(1, 16):
            tempBand, tempGeoTransform, tempProj, tempCols, tempRows = return_band(greenupList[greenupFile], 1)
            oneRowPixels = np.vstack([oneRowPixels, tempBand[i, :]])
        del tempBand, tempGeoTransform, tempProj, tempCols, tempRows
        for j in range(0, cols0):
            oneColumnPixels = list(oneRowPixels[:, j])
            if (any(element == 32767 for element in oneColumnPixels)):
                while 32767 in oneColumnPixels: oneColumnPixels.remove(32767)
            validValues = remove_outlier(oneColumnPixels)
            validValues = np.asarray(validValues)
            if (all(i > 0 for i in validValues)):
                GT_Zero = 1
            else:
                GT_Zero = 0
            if (all(i < 0 for i in validValues)):
                LT_Zero = 1
            else:
                LT_Zero = 0
            if ((validValues.size > limitCount and GT_Zero == 1) or (validValues.size > limitCount and LT_Zero == 1)):
                xSeries = np.asarray(range(1, validValues.size + 1, 1))  # generating x variable (1,2...)
                slope, intercept, r_value, p_value, std_err = stats.linregress(xSeries, validValues)
                band0[i, j] = round(slope, 2) * 100
                if (p_value < 0.001):
                    pValueList.append(1)
                elif (p_value < 0.005 and p_value >= 0.001):
                    pValueList.append(5)
                elif ((p_value < 0.05 and p_value >= 0.005)):
                    pValueList.append(50)
                else:
                    pValueList.append(0)
                meanList.append(int(round(np.mean(validValues), 0)))
                medList.append(int(round(np.median(validValues), 0)))
                sdList.append(int(round(np.std(validValues), 2) * 100))
            else:
                band0[i, j] = 32767
                pValueList.append(32767)
                meanList.append(32767)
                medList.append(32767)
                sdList.append(32767)

        with open("B1_TempP-Value.txt", "ab") as f_pValue:
            np.savetxt(f_pValue, pValueList, delimiter=',', fmt='% 5d')
        with open("B1_TempMean.txt", "ab") as f_Mean:
            np.savetxt(f_Mean, meanList, delimiter=',', fmt='% 5d')
        with open("B1_TempMedian.txt", "ab") as f_Med:
            np.savetxt(f_Med, medList, delimiter=',', fmt='% 5d')
        with open("B1_TempSD.txt", "ab") as f_SD:
            np.savetxt(f_SD, sdList, delimiter=',', fmt='% 5d')

    output_file(trendName, band0, geoTransform0, proj0, cols0, rows0)
    band0 = None

    read_pValue_Data = np.loadtxt("B1_TempP-Value.txt", delimiter=',', dtype=np.int16)
    pValue_Data = read_pValue_Data.reshape(rows0, cols0)
    read_pValue_Data = None
    output_file(pValueName, pValue_Data, geoTransform0, proj0, cols0, rows0)
    pValue_Data = None

    read_Mean_Data = np.loadtxt("B1_TempMean.txt", delimiter=',', dtype=np.int16)
    mean_Data = read_Mean_Data.reshape(rows0, cols0)
    read_Mean_Data = None
    output_file(meanName, mean_Data, geoTransform0, proj0, cols0, rows0)
    mean_Data = None

    read_Med_Data = np.loadtxt("B1_TempMedian.txt", delimiter=',', dtype=np.int16)
    med_Data = read_Med_Data.reshape(rows0, cols0)
    read_Med_Data = None
    output_file(medName, med_Data, geoTransform0, proj0, cols0, rows0)
    med_Data = None

    read_SD_Data = np.loadtxt("B1_TempSD.txt", delimiter=',', dtype=np.int16)
    SD_Data = read_SD_Data.reshape(rows0, cols0)
    read_SD_Data = None
    output_file(sdName, SD_Data, geoTransform0, proj0, cols0, rows0)
    SD_Data = None


## making the statistics of greenup metrics (Band2, 2001-2016) at each pixel, including
## including coefficient of linear regression, p-value, mean, median and standard deviation
def CalB2_GreenupStat(greenupList, limitCount, trendName, pValueName, meanName, medName, sdName):
    band0, geoTransform0, proj0, cols0, rows0 = return_band(greenupList[0], 1)

    open("B2_TempP-Value.txt", "w").close()
    open("B2_TempMean.txt", "w").close()
    open("B2_TempMedian.txt", "w").close()
    open("B2_TempSD.txt", "w").close()

    for i in range(0, rows0):
        print i
        oneRowPixels = band0[i, :]
        pValueList = []
        meanList = []
        medList = []
        sdList = []
        for greenupFile in range(1, 16):
            tempBand, tempGeoTransform, tempProj, tempCols, tempRows = return_band(greenupList[greenupFile], 1)
            oneRowPixels = np.vstack([oneRowPixels, tempBand[i, :]])
        del tempBand, tempGeoTransform, tempProj, tempCols, tempRows
        for j in range(0, cols0):
            oneColumnPixels = list(oneRowPixels[:, j])
            if (any(element == 32767 for element in oneColumnPixels)):
                while 32767 in oneColumnPixels: oneColumnPixels.remove(32767)
            validValues = remove_outlier(oneColumnPixels)
            validValues = np.asarray(validValues)
            if (all(i > 0 for i in validValues)):
                GT_Zero = 1
            else:
                GT_Zero = 0
            if (all(i < 0 for i in validValues)):
                LT_Zero = 1
            else:
                LT_Zero = 0
            if ((validValues.size > limitCount and GT_Zero == 1) or (validValues.size > limitCount and LT_Zero == 1)):
                xSeries = np.asarray(range(1, validValues.size + 1, 1))  # generating x variable (1,2...)
                slope, intercept, r_value, p_value, std_err = stats.linregress(xSeries, validValues)
                band0[i, j] = round(slope, 2) * 100
                if (p_value < 0.001):
                    pValueList.append(1)
                elif (p_value < 0.005 and p_value >= 0.001):
                    pValueList.append(5)
                elif ((p_value < 0.05 and p_value >= 0.005)):
                    pValueList.append(50)
                else:
                    pValueList.append(0)
                meanList.append(int(round(np.mean(validValues), 0)))
                medList.append(int(round(np.median(validValues), 0)))
                sdList.append(int(round(np.std(validValues), 2) * 100))
            else:
                band0[i, j] = 32767
                pValueList.append(32767)
                meanList.append(32767)
                medList.append(32767)
                sdList.append(32767)

        with open("B2_TempP-Value.txt", "ab") as f_pValue:
            np.savetxt(f_pValue, pValueList, delimiter=',', fmt='% 5d')
        with open("B2_TempMean.txt", "ab") as f_Mean:
            np.savetxt(f_Mean, meanList, delimiter=',', fmt='% 5d')
        with open("B2_TempMedian.txt", "ab") as f_Med:
            np.savetxt(f_Med, medList, delimiter=',', fmt='% 5d')
        with open("B2_TempSD.txt", "ab") as f_SD:
            np.savetxt(f_SD, sdList, delimiter=',', fmt='% 5d')

    output_file(trendName, band0, geoTransform0, proj0, cols0, rows0)
    band0 = None

    read_pValue_Data = np.loadtxt("B2_TempP-Value.txt", delimiter=',', dtype=np.int16)
    pValue_Data = read_pValue_Data.reshape(rows0, cols0)
    read_pValue_Data = None
    output_file(pValueName, pValue_Data, geoTransform0, proj0, cols0, rows0)
    pValue_Data = None

    read_Mean_Data = np.loadtxt("B2_TempMean.txt", delimiter=',', dtype=np.int16)
    mean_Data = read_Mean_Data.reshape(rows0, cols0)
    read_Mean_Data = None
    output_file(meanName, mean_Data, geoTransform0, proj0, cols0, rows0)
    mean_Data = None

    read_Med_Data = np.loadtxt("B2_TempMedian.txt", delimiter=',', dtype=np.int16)
    med_Data = read_Med_Data.reshape(rows0, cols0)
    read_Med_Data = None
    output_file(medName, med_Data, geoTransform0, proj0, cols0, rows0)
    med_Data = None

    read_SD_Data = np.loadtxt("B2_TempSD.txt", delimiter=',', dtype=np.int16)
    SD_Data = read_SD_Data.reshape(rows0, cols0)
    read_SD_Data = None
    output_file(sdName, SD_Data, geoTransform0, proj0, cols0, rows0)
    SD_Data = None


def ExtractSiteValues(timeSign, region_Input, sites_Input, SOS_Input, trend_Input, pValue_Input, sd_Input, buff_TH, erase_TH,
                          pValue_TH, SD_TH):
    strBuff_TH = str(buff_TH) + " Kilometers"
    strErase_TH = str(erase_TH) + " Kilometers"

    # removing duplicated sites with the same name, latitude and longitude
    arcpy.DeleteIdentical_management(sites_Input, ["place_name", "latitude","longitude"])

    ## generating the buffer
    sitesBuff_OutputName = sites_Input.replace(".shp", "_" + str(buff_TH) + "_" + str(erase_TH) + "_Buff.shp")
    if (erase_TH > 0 and erase_TH < buff_TH):
        arcpy.Buffer_analysis(sites_Input, "tempBuffer.shp", strBuff_TH)
        arcpy.Buffer_analysis(sites_Input, "tempErase.shp", strErase_TH)
        arcpy.Erase_analysis("tempBuffer.shp", "tempErase.shp", sitesBuff_OutputName)
    elif (erase_TH == 0):
        arcpy.Buffer_analysis(sites_Input, sitesBuff_OutputName, strBuff_TH)
    else:
        print ("Please using an effective radius to define buffer!")

    meanBuffPoint_OutputName = region_Input.split("\\")[-1].replace(".shp", "_Sites_Buff_" + str(buff_TH) + "_" + str(erase_TH) + "_Mean_Point.shp")
    trendBuffPoint_OutputName = region_Input.split("\\")[-1].replace(".shp", "_Sites_Buff_" + str(buff_TH) + "_" + str(erase_TH) + "_Trend_Point.shp")

    meanBuff_OutputName = region_Input.split("\\")[-1].replace(".shp", "_Sites_Buff_" + str(buff_TH) + "_" + str(erase_TH) + "_Mean.tif")
    trendBuff_OutputName = region_Input.split("\\")[-1].replace(".shp", "_Sites_Buff_" + str(buff_TH) + "_" + str(erase_TH) + "_Trend.tif")

    suffixMean = "_" + timeSign + "_" + str(buff_TH) + "_" + str(erase_TH) + "_" + str(pValue_TH) + "_" + str(SD_TH) + "_Mean_Buff.shp"
    print suffixMean
    suffixTrend = "_" + timeSign + "_" + str(buff_TH) + "_" + str(erase_TH) + "_" + str(pValue_TH) + "_" + str(SD_TH) + "_Trend_Buff.shp"
    meanJoin_OutputName = region_Input.split("\\")[-1].replace(".shp", suffixMean)
    trendJoin_OutputName = region_Input.split("\\")[-1].replace(".shp", suffixTrend)


    if (pValue_TH == 0 and SD_TH == 0):
        meanBuff_Extract = ExtractByMask(SOS_Input, sitesBuff_OutputName)
        trendBuff_Extract = ExtractByMask(trend_Input, sitesBuff_OutputName)
        arcpy.CopyRaster_management(meanBuff_Extract, meanBuff_OutputName, "DEFAULTS", "", "32767", "", "", "16_BIT_SIGNED")
        arcpy.CopyRaster_management(trendBuff_Extract, trendBuff_OutputName, "DEFAULTS", "", "32767", "", "", "32_BIT_FLOAT")
        arcpy.RasterToPoint_conversion(meanBuff_Extract, meanBuffPoint_OutputName, "VALUE")
        arcpy.RasterToPoint_conversion(trendBuff_Extract, trendBuffPoint_OutputName, "VALUE")
        arcpy.SpatialJoin_analysis(meanBuffPoint_OutputName, sitesBuff_OutputName, meanJoin_OutputName,
                                   "JOIN_ONE_TO_MANY")
        arcpy.SpatialJoin_analysis(trendBuffPoint_OutputName, sitesBuff_OutputName, trendJoin_OutputName,
                                   "JOIN_ONE_TO_MANY")
        # meanStat = ZonalStatisticsAsTable(inZoneData, zoneField, meanBuff_Extract, meanStat_OutputName, "DATA", "ALL")
        # trendStat = ZonalStatisticsAsTable(inZoneData, zoneField, "tempIntTrend.tif", trendStat_OutputName, "DATA", "ALL")
    elif (pValue_TH == 0 and SD_TH > 0):
        meanBuff_Extract = ExtractByMask(SOS_Input, sitesBuff_OutputName)
        trendBuff_Extract = ExtractByMask(trend_Input, sitesBuff_OutputName)
        sdBuff_Extract = ExtractByMask(sd_Input, sitesBuff_OutputName)
        mean_sdFilter = Con(sdBuff_Extract <= SD_TH, meanBuff_Extract)
        trend_sdFilter = Con(sdBuff_Extract <= SD_TH, trendBuff_Extract)
        arcpy.CopyRaster_management(mean_sdFilter, meanBuff_OutputName, "DEFAULTS", "", "32767", "", "",
                                    "16_BIT_SIGNED")
        arcpy.CopyRaster_management(trend_sdFilter, trendBuff_OutputName, "DEFAULTS", "", "32767", "", "",
                                    "32_BIT_FLOAT")
        arcpy.RasterToPoint_conversion(mean_sdFilter, meanBuffPoint_OutputName, "VALUE")
        arcpy.RasterToPoint_conversion(trend_sdFilter, trendBuffPoint_OutputName, "VALUE")
        arcpy.SpatialJoin_analysis(meanBuffPoint_OutputName, sitesBuff_OutputName, meanJoin_OutputName,
                                   "JOIN_ONE_TO_MANY")
        arcpy.SpatialJoin_analysis(trendBuffPoint_OutputName, sitesBuff_OutputName, trendJoin_OutputName,
                                   "JOIN_ONE_TO_MANY")
    elif (pValue_TH > 0 and SD_TH == 0):
        meanBuff_Extract = ExtractByMask(SOS_Input, sitesBuff_OutputName)
        trendBuff_Extract = ExtractByMask(trend_Input, sitesBuff_OutputName)
        pValueBuff_Extract = ExtractByMask(pValue_Input, sitesBuff_OutputName)
        if (pValue_TH == 1):
            mean_pValueFilter = Con(pValueBuff_Extract == 1, meanBuff_Extract)
            trend_pValueFilter = Con(pValueBuff_Extract == 1, trendBuff_Extract)
        elif (pValue_TH == 5):
            mean_pValueFilter = Con((pValueBuff_Extract == 1) | (pValueBuff_Extract == 5), meanBuff_Extract)
            trend_pValueFilter = Con((pValueBuff_Extract == 1) | (pValueBuff_Extract == 5), trendBuff_Extract)
        elif (pValue_TH == 50):
            mean_pValueFilter = Con(pValueBuff_Extract != 0, meanBuff_Extract)
            trend_pValueFilter = Con(pValueBuff_Extract != 0, trendBuff_Extract)
        else:
            print "Invalid threshold ! "
            exit(1)
        arcpy.RasterToPoint_conversion(mean_pValueFilter, meanBuffPoint_OutputName, "VALUE")
        arcpy.RasterToPoint_conversion(trend_pValueFilter, trendBuffPoint_OutputName, "VALUE")
        arcpy.SpatialJoin_analysis(meanBuffPoint_OutputName, sitesBuff_OutputName, meanJoin_OutputName,
                                   "JOIN_ONE_TO_MANY")
        arcpy.SpatialJoin_analysis(trendBuffPoint_OutputName, sitesBuff_OutputName, trendJoin_OutputName,
                                   "JOIN_ONE_TO_MANY")
    elif (pValue_TH > 0 and SD_TH > 0):
        meanBuff_Extract = ExtractByMask(SOS_Input, sitesBuff_OutputName)
        trendBuff_Extract = ExtractByMask(trend_Input, sitesBuff_OutputName)
        pValueBuff_Extract = ExtractByMask(pValue_Input, sitesBuff_OutputName)
        sdBuff_Extract = ExtractByMask(sd_Input, sitesBuff_OutputName)
        if (pValue_TH == 1):
            temp_pValue_0 = Con(pValueBuff_Extract == 1, 1, 0)
            temp_pValue = Con(IsNull(temp_pValue_0), 0, temp_pValue_0)
        elif (pValue_TH == 5):
            temp_pValue_0 = Con((pValueBuff_Extract == 1) | (pValueBuff_Extract == 5), 1, 0)
            temp_pValue = Con(IsNull(temp_pValue_0), 0, temp_pValue_0)
        elif (pValue_TH == 50):
            temp_pValue_0 = Con(pValueBuff_Extract != 0, 1, 0)
            temp_pValue = Con(IsNull(temp_pValue_0), 0, temp_pValue_0)
        temp_SD_0 = Con(sdBuff_Extract <= SD_TH, 1, 0)
        temp_SD = Con(IsNull(temp_SD_0), 0, temp_SD_0)

        filterTemplate = temp_pValue + temp_SD
        mean_Filter = Con(filterTemplate == 2, meanBuff_Extract)
        trend_Filter = Con(filterTemplate == 2, trendBuff_Extract)

        arcpy.RasterToPoint_conversion(mean_Filter, meanBuffPoint_OutputName, "VALUE")
        arcpy.RasterToPoint_conversion(trend_Filter, trendBuffPoint_OutputName, "VALUE")
        arcpy.SpatialJoin_analysis(meanBuffPoint_OutputName, sitesBuff_OutputName, meanJoin_OutputName,
                                   "JOIN_ONE_TO_MANY")
        arcpy.SpatialJoin_analysis(trendBuffPoint_OutputName, sitesBuff_OutputName, trendJoin_OutputName,
                                   "JOIN_ONE_TO_MANY")
