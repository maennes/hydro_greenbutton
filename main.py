# Get electricity consumption data from Hydro One website.
# The time-based series are stored in InfluxDB.

# Requires username/password to their service at https://www.hydroone.com/myaccount/
# Also, needs the account ID and meter ID, which are available on
# regular bills (no spaces for account number)

# This script uses web scraping as Hydro One doesn't offer API access, AFAIK.

import json
import requests
import re
import time
import xmltodict
import datetime
import time
import urllib.parse
from pytz import timezone
from influxdb import InfluxDBClient

# Load secret data from locally encrypted file content.
# The data syntax is defined at https://docs.python.org/3/library/configparser.html
import sys
sys.path.insert(1, '../common_functions')
from creds import getSecrets
CREDS = getSecrets('192.168.1.10', '../config/creds.encrypted')

# Set parameters
HYDRO_USERNAME = CREDS.get('Hydro One', 'username')
HYDRO_PASSWORD = CREDS.get('Hydro One', 'password')
HYDRO_ACCOUNTID = CREDS.get('Hydro One', 'accountid')
HYDRO_METERID = CREDS.get('Hydro One', 'meterid')
INFLUXDB_HOST = CREDS.get('InfluxDB', 'host')
INFLUXDB_PORT = CREDS.get('InfluxDB', 'port')
INFLUXDB_USERNAME = CREDS.get('InfluxDB', 'username')
INFLUXDB_PASSWORD = CREDS.get('InfluxDB', 'password')
INFLUXDB_DATABASE = 'ext'

# Instantiate database
influxClient = InfluxDBClient(
    host=INFLUXDB_HOST,
    port=INFLUXDB_PORT,
    username=INFLUXDB_USERNAME,
    password=INFLUXDB_PASSWORD,
    database=INFLUXDB_DATABASE
)

def getDateTimeByZone(tz):
    t = timezone(tz)
    return datetime.datetime.now(t)
    
def printme( str ):
    t = getDateTimeByZone('US/Eastern')
    print (t.strftime("%Y-%m-%d %H:%M:%S"), str)
    return

def extractHidden(s, flag):
    pattern = re.compile('<input type="hidden".*?/>')
    result = ''
    for m in re.findall(pattern, s):
        nameObject = re.search('name=".*?"', m)
        nameString = re.search('".*?"', nameObject.group(0)).group(0).replace('"', '')
        valueObject = re.search('value=".*?"', m)
        valueString = re.search('".*?"', valueObject.group(0)).group(0).replace('"', '')
        if flag == 1:
            valueString = urllib.parse.quote_plus(valueString)
        result += '&' + nameString + "=" + valueString
    return result

def extractInputFromList(s, listOfNames):
    pattern = re.compile('<input .*?/>')
    result = ''
    for m in re.findall(pattern, s):
        nameObject = re.search('name=".*?"', m)
        try:
            nameString = re.search('".*?"', nameObject.group(0)).group(0).replace('"', '')
            valueObject = re.search('value=".*?"', m)
            valueString = re.search('".*?"', valueObject.group(0)).group(0).replace('"', '')
            if nameString in listOfNames:
                result += '&' + \
                    urllib.parse.quote_plus(nameString) + "=" + urllib.parse.quote_plus(valueString)
        except:
            printme("Failed for " + m)

    return result

def extractChartDataJSON(s):
    nameString = re.search(r'ChartDataJSON.*?\}"', s).group(0)
    f = nameString.find('"{')
    nameString = nameString[f+1:-1]
    nameString = nameString.replace('&quot;', '"')
    return json.loads(nameString)

def intervalBlocks(tos, offset, blocks):
    json_body = []
    for IntervalBlock in blocks :
        for IntervalReading in IntervalBlock['IntervalReading'] :
            if isinstance(IntervalReading, dict):
                json_body.append({
                    "measurement": "electricity",
                    "tags": {
                        "source": "hydro_one",
                        "time_of_use": tos                    },
                    "time": datetime.datetime.utcfromtimestamp(int(IntervalReading['timePeriod']['start']) + offset),
                    "fields": {
                        "cost": round(int(IntervalReading['cost'])/100000, 3),
                        "kwh": round(int(IntervalReading['value'])/1000000, 4),
                        "duration": int(IntervalReading['timePeriod']['duration']) * 1
                    }
                })

    return json_body
                
def main():

    printme('Getting Hydro One information')
    session = requests.Session()

    printme("Authenticating")
    r = session.post(
        "https://www.myaccount.hydroone.com/pkmslogin.form",
        data=("username=" + HYDRO_USERNAME + "&password=" +
              HYDRO_PASSWORD + "&UserId=&login-form-type=pwd"),
        headers={"Accept" : "text/html, application/xhtml+xml, image/jxr, */*", "Content-Type" : "application/x-www-form-urlencoded"}
    )
    # Verify authentication was successful by looking for meta tag with redirect to login page
    if 'https://www.hydroone.com/login?' in r.text:
        printme(f"Found meta redirect to 'https://www.hydroone.com/login?' in response. Looks like the authentication failed. Aborting ...")
        exit(0)

    printme("Federating")
    sSSO = session.get(
        "https://www.myaccount.hydroone.com/FIM/sps/WSFedPassiveX/wsf?wa=wsignin1.0&wtrealm=urn%3aecustomer%3aprod&wctx=https%3a%2f%2fwww.hydroone.com%2fMyAccount_%2fSecure%2f_layouts%2f15%2fAuthenticate.aspx%3fSource%3d%252Fmyaccount%252Fsecure",
        headers={"Accept" : "text/html, application/xhtml+xml, image/jxr, */*"}
    )

    printme("Trusting")
    session.post(
        "https://www.hydroone.com/_trust/",
        data=(extractHidden(sSSO.text, 1)),
        headers={"Accept" : "text/html, application/xhtml+xml, image/jxr, */*", "Content-Type" : "application/x-www-form-urlencoded"},
        verify=True
    )

    printme("Going to SharePoint site for My Energy Usage")
    r = session.post(
        "https://www.myaccount.hydroone.com/TOUPortal/SSOTarget.aspx",
        headers={"Accept" : "text/html, application/xhtml+xml, image/jxr, */*", "Content-Type" : "application/x-www-form-urlencoded"},
        data=('accountid=' + HYDRO_ACCOUNTID)
    )
    
    printme("Getting default page with daily JSON embedded")
    session.get(
        "https://www.myaccount.hydroone.com/TOUPortal/Post.aspx",
        headers={
            "Accept": "text/html, application/xhtml+xml, image/jxr, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36 Edge/16.16299",
            "Accept-Encoding": "gzip, deflate, br",
            "Host": "www.myaccount.hydroone.com",
            "Connection": "Keep-Alive"
        }
    )
    
    printme("Getting Greenbutton xml")
    numberOfDays = 14
    endUnixTime = int(time.mktime(datetime.date.today().timetuple()))
    startUnixTime = endUnixTime -  (numberOfDays * 86400) 
    startDate = str((startUnixTime * 10000000) + 621355968000000000)
    endDate = str((endUnixTime * 10000000) + 621355968000000000)
    url = "https://www.myaccount.hydroone.com/TOUPortal/DownloadData.aspx?timeFormat=hourly&startDate=" + \
        startDate + "&endDate=" + endDate
    # printme(f"-> {url}")
    sGreenButton = session.get(url,
        headers={"Accept": "text/html, application/xhtml+xml, image/jxr, */*",
            "X-Requested-With": "XMLHttpRequest"}
        )

    
    # Parse the xml into an object
    # with open('greenbutton.txt', 'w') as f:
    #     f.writelines(sGreenButton.text)
    doc = xmltodict.parse(sGreenButton.text)
    
    # Read the time zone offset form the xml
    # tzOffset = int(doc['feed']['entry'][1]['content']['LocalTimeParameters']['tzOffset'] )

    for entry in doc['feed']['entry']:

        if '/RetailCustomer/1/UsagePoint/' + HYDRO_METERID + '/MeterReading/1/IntervalBlock/1' in entry['link'][0]['@href']:
            printme(f"-> On-Peak: {len(entry['content']['IntervalBlock'])} entries found")
            influxClient.write_points(intervalBlocks(
                'On-Peak', 0, entry['content']['IntervalBlock']))

        elif '/RetailCustomer/1/UsagePoint/' + HYDRO_METERID + '/MeterReading/2/IntervalBlock/2' in entry['link'][0]['@href']:
            printme(
                f"-> Mid-Peak: {len(entry['content']['IntervalBlock'])} entries found")
            influxClient.write_points(intervalBlocks(
                'Mid-Peak', 0, entry['content']['IntervalBlock']))

        elif '/RetailCustomer/1/UsagePoint/' + HYDRO_METERID + '/MeterReading/3/IntervalBlock/3' in entry['link'][0]['@href']:
            printme(
                f"-> Off-Peak: {len(entry['content']['IntervalBlock'])} entries found")
            influxClient.write_points(intervalBlocks(
                'Off-Peak', 0, entry['content']['IntervalBlock']))

    printme("Logging out")
    session.get(
        "https://www.hydroone.com/_layouts/15/SignOut.aspx",
        headers={"Accept" : "text/html, application/xhtml+xml, image/jxr, */*"}
    )

    printme('Finished')

if __name__== "__main__":
    main()
