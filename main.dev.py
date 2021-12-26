# Get electricity consumption data from Hydro One website.
# The time-based series are stored in InfluxDB.

# Requires username/password to their service at https://www.hydroone.com/myaccount/
# Also, needs the account ID and meter ID, which are available on
# regular bills (no spaces for account number)

# This script uses web scraping as Hydro One doesn't offer API access, AFAIK.

import json
import requests
import re
import datetime
import urllib.parse
from pytz import timezone
from influxdb import InfluxDBClient
from bs4 import BeautifulSoup

# Load secret data from locally encrypted file content.
# The data syntax is defined at https://docs.python.org/3/library/configparser.html
import sys
if sys.platform == 'win32':
    DIRECTORY_GITHUB = '\\\\nas01\\GitHub\\'
    DIRECTORY_FUNCTIONS = f"{DIRECTORY_GITHUB}\\common_functions\\"
    DIRECTORY_CONFIG = f"{DIRECTORY_GITHUB}\\config\\"
elif sys.platform == 'linux':
    DIRECTORY_GITHUB = '/nas01/GitHub/'
    DIRECTORY_FUNCTIONS = f"{DIRECTORY_GITHUB}common_functions/"
    DIRECTORY_CONFIG = f"{DIRECTORY_GITHUB}config/"
CREDS_ENCRYPTED = f"{DIRECTORY_CONFIG}creds.encrypted"
sys.path.insert(1, DIRECTORY_FUNCTIONS)
from creds import getSecrets
CREDS = getSecrets('192.168.1.10', CREDS_ENCRYPTED)

# Set parameters
HYDRO_USERNAME = CREDS.get('Hydro One', 'username')
HYDRO_PASSWORD = CREDS.get('Hydro One', 'password')
HYDRO_ACCOUNTID = CREDS.get('Hydro One', 'accountid')
HYDRO_METERID = CREDS.get('Hydro One', 'meterid')
HYDRO_HEALTHCHECK_URL = CREDS.get('Hydro One', 'healthcheckUrl')
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

def processChartData(strHtml, strPeriod):
    soup = BeautifulSoup(strHtml, 'html.parser')
    try:
        j = json.loads(soup.select("input#ChartDataJSON")[0]['value'])
        printme(f"-> Found {len(j['timePoints'])} data items")
        json_body = []
        for t in j['usage']:
            for i in range(len(j['timePoints'])):
                json_body.append({
                    "measurement": "electricity",
                    "tags": {
                        "source": "Hydro One",
                        "period": strPeriod,
                        "pricing": t['name']
                    },
                    "time": datetime.datetime.utcfromtimestamp(j['timePoints'][i]),
                    "fields": {
                        "kWh": t['data'][i]['y'],
                        "cost": t['data'][i]['cost']
                    }
                })
        influxClient.write_points(json_body)

    except Exception as e:
        if hasattr(e, 'message'):
            printme(e.message)
        else:
            printme(e)
        exit(0)
    
def do_work():

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
    session.get(
        "https://www.myaccount.hydroone.com/FIM/sps/WSFedPassiveX/wsf?wa=wsignin1.0&wtrealm=urn%3aecustomer%3aprod&wctx=https%3a%2f%2fwww.hydroone.com%2fMyAccount_%2fSecure%2f_layouts%2f15%2fAuthenticate.aspx%3fSource%3d%252Fmyaccount%252Fsecure",
        headers={"Accept" : "text/html, application/xhtml+xml, image/jxr, */*"}
    )

    printme("Trusting")
    session.post(
        "https://www.hydroone.com/_trust/",
        headers={"Accept" : "text/html, application/xhtml+xml, image/jxr, */*", "Content-Type" : "application/x-www-form-urlencoded"},
        verify=True
    )

    printme("Going to SharePoint site for My Energy Usage")
    session.post(
        "https://www.myaccount.hydroone.com/TOUPortal/SSOTarget.aspx",
        headers={"Accept" : "text/html, application/xhtml+xml, image/jxr, */*", "Content-Type" : "application/x-www-form-urlencoded"},
        data=('accountid=' + HYDRO_ACCOUNTID)
    )
    
    printme("Getting default page")
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

    periods = ['Hourly', 'Daily', 'Monthly']
    for period in periods:
        printme(f"Getting {period} page with chart data")
        r = session.post(
            f"https://www.myaccount.hydroone.com/TOUPortal/{period}.aspx",
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "Accept-Language": "en-US,en;q=0.5",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36 Edge/16.16299",
                "Accept-Encoding": "gzip, deflate, br",
                "Host": "www.myaccount.hydroone.com",
                "Connection": "Keep-Alive"
            }
        )
        processChartData(r.text, period)
    
    printme("Logging out")
    session.get(
        "https://www.hydroone.com/_layouts/15/SignOut.aspx",
        headers={"Accept" : "text/html, application/xhtml+xml, image/jxr, */*"}
    )

    printme('Finished')
    return True


def main():

    # An alert will come from healthchecks.io if not executed every day
    requests.get(HYDRO_HEALTHCHECK_URL + "/start")

    success = False
    try:
        success = do_work()
    finally:
        # On success, requests https://hc-ping.com/your-uuid-here
        # On failure, requests https://hc-ping.com/your-uuid-here/fail
        r = requests.get(
            HYDRO_HEALTHCHECK_URL if success else HYDRO_HEALTHCHECK_URL + "/fail")
        printme(f"healthchecks.io request was received {r.text}")

if __name__ == "__main__":
    main()
