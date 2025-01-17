from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum,avg, desc, row_number, asc, max, month, dayofmonth, hour,round,floor,dayofweek,udf
from pyspark.sql.types import StringType
import sys,time,os
from pyspark.sql.window import Window
from pyspark.sql.functions import col


spark = SparkSession.builder.master("spark://192.168.0.2:7077").appName("advDB").getOrCreate()
print("spark session created")

# Path to the data
hdfs_path = "hdfs://192.168.0.2:9000/user/user/data/"


# Read the Parquet files from HDFS and create a dataframe
df_taxi_trips = spark.read.parquet(hdfs_path + "yellow_tripdata_2022-01.parquet", hdfs_path + "yellow_tripdata_2022-02.parquet", hdfs_path + "yellow_tripdata_2022-03.parquet", hdfs_path + "yellow_tripdata_2022-04.parquet", hdfs_path + "yellow_tripdata_2022-05.parquet", hdfs_path + "yellow_tripdata_2022-06.parquet")


# create the rdd from the dataframe
rdd_taxi_trips = df_taxi_trips.rdd


# read csv file
df_taxi_zone_lookup = spark.read.csv(hdfs_path + "taxi_zone_lookup.csv")

# Create an RDD from dataframe 
rdd_taxi_zone_lookup = df_taxi_zone_lookup.rdd


# Query 1

start_Q1 = time.time()

# Να βρεθεί η διαδρομή με το μεγαλύτερο φιλοδώρημα (tip)τον Μάρτιο και σημείο άφιξης το "BatteryPark"
df_taxi_trips.filter(month(col("tpep_pickup_datetime")) == 3)\
    .join(df_taxi_zone_lookup, [df_taxi_trips.DOLocationID == df_taxi_zone_lookup._c0, df_taxi_zone_lookup._c2 == "Battery Park"])\
    .sort(desc("tip_amount"))\
    .drop("_c0","_c1","_c2","_c3")\
    .show(1)


end_Q1 = time.time()
print(f'Q1 time taken: {end_Q1-start_Q1} seconds.')


# Query 2

start_Q2 = time.time()

# Να βρεθεί,για κάθε μήνα,η διαδρομή με το υψηλότερο ποσό στα διόδια. Αγνοήστε μηδενικά ποσά
df_taxi_trips.filter(col("Tolls_amount") > 0)\
.groupBy(month(col("tpep_pickup_datetime")))\
.agg(max("Tolls_amount")\
.alias("max_Tolls_amount"))\
.sort(asc("month(tpep_pickup_datetime)"))\
.join(df_taxi_trips, [month(col("tpep_pickup_datetime")) == col("month(tpep_pickup_datetime)"), col("Tolls_amount") == col("max_Tolls_amount")])\
.drop("month(tpep_pickup_datetime)","max_Tolls_amount")\
.show()

end_Q2 = time.time()

print(f'Q2 time taken: {end_Q2-start_Q2} seconds.')

# Query 3

#Να βρεθεί, ανά15 ημέρες,ο μέσος όρος της απόστασης και του κόστους για όλες τις διαδρομές με σημείο αναχώρησης διαφορετικό από το σημείο άφιξης.
start_Q3_DF = time.time()

df_taxi_trips.filter(col("PULocationID") != col("DOLocationID"))\
.groupBy([dayofmonth(col("tpep_pickup_datetime")),month(col("tpep_pickup_datetime"))])\
.agg(avg("trip_distance").alias("avg_trip_distance"),avg("total_amount").alias("avg_total_amount"))\
.sort(asc("month(tpep_pickup_datetime)"),asc("dayofmonth(tpep_pickup_datetime)"))\
.withColumn("index", row_number().over(Window.orderBy("month(tpep_pickup_datetime)","dayofmonth(tpep_pickup_datetime)")))\
.withColumn("group", floor((col("index")-1)/15))\
.groupBy("group")\
.agg(round(avg("avg_trip_distance"),2).alias("15_day_avg_trip_distance"),round(avg("avg_total_amount"),2).alias("15_day_avg_total_amount"))\
.show()

end_Q3_DF = time.time()

print(f'Q3_DF time taken: {end_Q3_DF-start_Q3_DF} seconds.')

#Να βρεθεί, ανά15 ημέρες,ο μέσος όρος της απόστασης και του κόστους για όλες τις διαδρομές με σημείο αναχώρησης διαφορετικό από το σημείο άφιξης.
# using RDD

start_Q3_RDD = time.time()

print(rdd_taxi_trips.filter(lambda x: x.PULocationID != x.DOLocationID)\
.map(lambda x: ((x.tpep_pickup_datetime.day,x.tpep_pickup_datetime.month),(float(x.trip_distance),float(x.total_amount),1)))\
.reduceByKey(lambda x,y: (x[0]+y[0],x[1]+y[1],x[2]+y[2]))\
.map(lambda x: (x[0],(x[1][0]/x[1][2],x[1][1]/x[1][2])))\
.sortBy(lambda x: (x[0][1],x[0][0]))\
.zipWithIndex()\
.map(lambda x: (int(str(x[1]/15)[0]),(x[0][1][0],x[0][1][1],1)))\
.reduceByKey(lambda x,y: (x[0]+y[0],x[1]+y[1],x[2]+y[2]))\
.map(lambda x: (x[0],(x[1][0]/x[1][2],x[1][1]/x[1][2])))\
.sortByKey()\
.take(20))


end_Q3_RDD = time.time()

print(f'Q3_RDD time taken: {end_Q3_RDD-start_Q3_RDD} seconds.')

# Query 4

#Να βρεθούν οι τρεις μεγαλύτερες (top3)ώρες αιχμής ανάημέρα της εβδομάδος, εννοώντας τις ώρες (π.χ., 7-8πμ, 3-4μμ, κλπ) της ημέρας με τον μεγαλύτερο αριθμό επιβατών σε μια κούρσα ταξί.Ο υπολογισμός αφορά όλους τους μήνες

start_Q4 = time.time()

# find the top 3 hours of the day with the most passengers in a taxi
df_taxi_trips.groupBy([dayofweek(col("tpep_pickup_datetime")), hour(col("tpep_pickup_datetime"))])\
.agg(max("Passenger_count").alias("max_passenger_count"))\
.withColumn("index", row_number().over(Window.partitionBy("dayofweek(tpep_pickup_datetime)").orderBy(desc("max_passenger_count"))))\
.filter(col("index") <= 3)\
.sort(asc("dayofweek(tpep_pickup_datetime)"),asc("index"))\
.show()

end_Q4 = time.time()

print(f'Q4 time taken: {end_Q4-start_Q4} seconds.')

# Query 5

start_Q5 = time.time()

# Να βρεθούν οι κορυφαίες πέντε (top 5) ημέρες ανά μήνα στις οποίες οι κούρσες είχαν το μεγαλύτερο ποσοστό σε tip
df_taxi_trips.groupBy([month(col("tpep_pickup_datetime")), dayofmonth(col("tpep_pickup_datetime"))])\
.agg(sum("Fare_amount").alias("sum_fare_amount"), sum("Tip_amount").alias("sum_tip_amount"))\
.withColumn("tip_percentage", col("sum_tip_amount")/col("sum_fare_amount"))\
.withColumn("index", row_number().over(Window.partitionBy("month(tpep_pickup_datetime)").orderBy(desc("tip_percentage"))))\
.filter(col("index") <= 5)\
.sort(asc("month(tpep_pickup_datetime)"),asc("index"))\
.drop("sum_fare_amount", "sum_tip_amount")\
.show(100)

end_Q5 = time.time()

print(f'Q5 time taken: {end_Q5-start_Q5} seconds.')






