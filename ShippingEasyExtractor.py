from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import ElementNotVisibleException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.common.exceptions import WebDriverException
from requestium import Session, Keys
import json
from bs4 import BeautifulSoup
import sys
import os
import datetime
import csv
import traceback
import time

import pymysql.cursors


session = None
log_filename = None
result_filename = None
currentDT = None


def openConnection():
    connection = pymysql.connect(host='localhost',
                             user='app',
                             password='HatAndBeyond123!',
                             db='hdb',
                             connect_timeout=5,
                             charset='utf8',
                             cursorclass=pymysql.cursors.DictCursor)
    return connection


def login(username_str, password_str, show_ui):
    global session
    if show_ui == False:
        session = Session('chromedriver',
                      browser='chrome',
                      default_timeout=15,
                      webdriver_options={'arguments': ['headless',
                                                       'disable-gpu',
                                                       '--ignore-certificate-errors',
                                                       '--ignore-ssl-errors']})
    else:
        session = Session('chromedriver',
                      browser='chrome',
                      default_timeout=15,
                      webdriver_options={'arguments': ['disable-gpu',
                                                       '--ignore-certificate-errors',
                                                       '--ignore-ssl-errors']})

    session.driver.get(('https://app.shippingeasy.com/login'))

    username = session.driver.find_element_by_id('user_email')
    username.send_keys(username_str)
    password = session.driver.find_element_by_id('user_password')
    password.send_keys(password_str)
    button = session.driver.find_element_by_xpath("//input[@type='submit']")
    button.click()

    session.transfer_driver_cookies_to_session()
    bLogin = True
    return bLogin


def extract_orders(market_meta):
    orders = []
    order_item = []
    pageNum = 0
    while True:
        try:
            session.transfer_driver_cookies_to_session()
            pageNum = pageNum + 1
            order_url = 'https://app1.shippingeasy.com/orders?page={0}&paging=t&search_form%5Bper_page%5D=200'.format(pageNum)
            response = session.get(order_url)
            session.driver.get(order_url)
            try:
                table_ele = WebDriverWait(session.driver, 10).until(EC.presence_of_element_located((By.XPATH, "//table[@class='se-table instant-rate-enabled orders']")))
                print("Page is ready!")

                tr_eles = table_ele.find_element_by_tag_name('tbody').find_elements_by_tag_name('tr')
                
                if len(tr_eles) < 1:
                    break

                for tr_ele in tr_eles:
                    soup = BeautifulSoup(tr_ele.get_attribute('innerHTML').strip('\n '), 'html.parser')
                    td_eles = soup.find_all('td')

                    product = {
                        "CHANNEL_ORDER_NO": td_eles[6].find('a', class_='order-link').text.strip('\n '),
                        "ORDER_QTY": td_eles[10].text.strip('\n '),
                        "ORDER_PRICE": td_eles[8].text.strip('\n $'),
                        "SHIPPING_PRICE": td_eles[9].text.strip('\n $')
                    }

                    date_str = td_eles[7].text.strip('\n ').lower()
                    product["ORDER_DATE"] = get_date_from_date_str(date_str)

                    market_str = td_eles[5].text.strip('\n ').lower()
                    product['MARKET_ID'] = get_channel_from_market_str(market_meta, market_str)

                    orders.append(product)

                    if td_eles[11].find('a', class_='multi-item-toggle') != None:
                        session.transfer_driver_cookies_to_session()
                        anchor_id = td_eles[11].find('a', class_='multi-item-toggle').attrs['id']
                        response = session.get('https://app1.shippingeasy.com/orders/line_items/{0}'.format(anchor_id[anchor_id.rfind('_')+1:]))
                        item_trs = BeautifulSoup(response.text, 'html.parser').find('table', class_='table table-bordered').find('tbody').find_all('tr')
                        for item_tr in item_trs:
                            item_td_eles = item_tr.find_all('td')
                            order_item.append({
                                "CHANNEL_ORDER_NO": product["CHANNEL_ORDER_NO"],
                                "MARKET_ID": product["MARKET_ID"],
                                "LISTING_SKU": item_td_eles[3].text.strip('\n :'),
                                "UNIT_PRICE": item_td_eles[4].text.strip('\n $'),
                                "UNIT_QTY": item_td_eles[1].text.strip('\n ')
                            })
                    else:
                        order_item.append({
                            "CHANNEL_ORDER_NO": product["CHANNEL_ORDER_NO"],
                            "MARKET_ID": product["MARKET_ID"],
                            "LISTING_SKU": td_eles[12].text.strip('\n :'),
                            "UNIT_PRICE": product["ORDER_PRICE"],
                            "UNIT_QTY": 1
                        })
            except TimeoutException:
                print("Loading took too much time!")
        except Exception as exception:
            traceback.print_exc()
            break

    return orders, order_item


def get_date_from_date_str(date_str):
    month_str = date_str[:date_str.find(' ')].lower()[:3]
    day_str = date_str[date_str.find(' ')+1:]

    month_str_to_num = {
        'jan': 1,
        'feb': 2,
        'mar': 3,
        'apr': 4,
        'may': 5,
        'jun': 6,
        'jul': 7,
        'aug': 8,
        'sep': 9,
        'oct': 10,
        'nov': 11,
        'dec': 12
    }

    d = datetime.date(datetime.date.today().year, month_str_to_num[month_str], int(day_str))
    return d.strftime('%Y%m%d')


def get_channel_from_market_str(market_meta, market_str):
    brand = ''
    if -1 < market_str.find('croix'):
        brand = 'croix'
    elif -1 < market_str.find('beyond'):
        brand = 'beyond'
    elif -1 < market_str.find('skyhigh'):
        brand = 'skyhigh'
    else:
        brand = 'manual'
    
    channel = ''
    if -1 < market_str.find('amazon'):
        channel = 'amazon'
    elif -1 < market_str.find('ebay'):
        channel = 'ebay'
    elif -1 < market_str.find('walmart'):
        channel = 'walmart'
    elif -1 < market_str.find('skyhigh'):
        channel = 'ebay'
    elif -1 < market_str.find('beyond'):
        channel = 'shopify'
    else:
        channel = 'manual'

    for market in market_meta:
        if -1 < market['CHANNEL_NM'].lower().find(channel) and -1 < market['BRAND_NM'].lower().find(brand):
            return market['MARKET_ID']

    return 99 # manual order


def write_log(msg, file_name):
    print(msg)
    with open(file_name, mode='a+') as log_file:
        log_file.write(msg+'\n')


def run(file_name):
    global log_filename
    global result_filename
    global currentDT

    log_filename = 'ShippingEasyExtraction_{0}.log'.format(currentDT.strftime("%Y%m%d_%H%M%S"))
    
    linked_sku_cnt = 0

    try:
        conn = openConnection()
        with conn.cursor() as cursor:
            # Read a single record
            sql = "SELECT `MARKET_ID`, `CHANNEL_NM`, `BRAND_NM`, `LISTING_MARKET_ID` FROM `MARKET`"
            cursor.execute(sql, ())
            market_meta = cursor.fetchall()

        orders, order_items = extract_orders(market_meta)

        if 0 < len(orders):
            write_log('Insert order data to database.', log_filename)

            conn.begin()
            with conn.cursor() as cursor:
                for order in orders:
                    try:
                        sql = "INSERT INTO `ORDER` (\
                                    `CHANNEL_ORDER_NO`\
                                    , `MARKET_ID`\
                                    , `ORDER_DATE`\
                                    , `ORDER_QTY`\
                                    , `ORDER_PRICE`\
                                    , `SHIPPING_PRICE`\
                                ) VALUES (%s, %s, %s, %s, %s, %s)"
                        cursor.execute(sql, (\
                            order['CHANNEL_ORDER_NO'], \
                            order['MARKET_ID'], \
                            order['ORDER_DATE'], \
                            order['ORDER_QTY'], \
                            order['ORDER_PRICE'], \
                            order['SHIPPING_PRICE']))
                    except pymysql.IntegrityError as error:
                        sql = "UPDATE `ORDER`\
                                  SET `ORDER_DATE` = %s\
                                    , `ORDER_QTY` = %s\
                                    , `ORDER_PRICE` = %s\
                                    , `SHIPPING_PRICE` = %s\
                                WHERE `CHANNEL_ORDER_NO` = %s\
                                  AND `MARKET_ID` = %s"
                        cursor.execute(sql, ( \
                            order['ORDER_DATE'], \
                            order['ORDER_QTY'], \
                            order['ORDER_PRICE'], \
                            order['SHIPPING_PRICE'], \
                            order['CHANNEL_ORDER_NO'], \
                            order['MARKET_ID']))
                # cursor.close()

            # with conn.cursor() as cursor:
                for order_item in order_items:
                    try:
                        sql = "INSERT INTO `ORDER_ITEM` (\
                                      `CHANNEL_ORDER_NO`\
                                    , `MARKET_ID`\
                                    , `LISTING_SKU`\
                                    , `UNIT_PRICE`\
                                    , `UNIT_QTY`\
                                ) VALUES (%s, %s, %s, %s, %s)"
                        cursor.execute(sql, (\
                            order_item['CHANNEL_ORDER_NO'], \
                            order_item['MARKET_ID'], \
                            order_item['LISTING_SKU'], \
                            order_item['UNIT_PRICE'], \
                            order_item['UNIT_QTY']))
                    except pymysql.IntegrityError as error:
                        sql = "UPDATE `ORDER_ITEM`\
                                  SET `UNIT_PRICE` = %s\
                                    , `UNIT_QTY` = %s\
                                WHERE `CHANNEL_ORDER_NO` = %s\
                                  AND `MARKET_ID` = %s\
                                  AND `LISTING_SKU` = %s"
                        cursor.execute(sql, ( \
                            order_item['UNIT_PRICE'], \
                            order_item['UNIT_QTY'], \
                            order_item['CHANNEL_ORDER_NO'], \
                            order_item['MARKET_ID'], \
                            order_item['LISTING_SKU']))
                
                conn.commit()
                cursor.close()

            with open('orders.{0}.csv'.format(currentDT.strftime("%Y%m%d_%H%M%S")), 'w', newline='', encoding='UTF8') as csvfile:
                fieldnames = list(orders[0].keys())
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for order in orders:
                    writer.writerow(order)

        with open('order_items.{0}.csv'.format(currentDT.strftime("%Y%m%d_%H%M%S")), 'w', newline='', encoding='UTF8') as csvfile:
            fieldnames = list(order_items[0].keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for order_item in order_items:
                writer.writerow(order_item)

        print(orders)
        print(order_items)
    except FileNotFoundError as error:
        write_log('{0}: {1}'.format(error.filename, error.strerror), log_filename)
    finally:
        conn.close()
    
    return linked_sku_cnt


if __name__ == '__main__':
    USER_NAME = 'jcsky.jaik@gmail.com'
    PASSWORD = 'Happy10*'
    input_file_name = ''
    SHOW_BROWSER = True

    TEST = 1

    if TEST != 1:
        if len(sys.argv) < 4:
            print('Usage: python LinkCreator.py <Input_file_name.csv> [USER_ID] [PASSWORD] [0/1:SHOW_BROWSER]')
            exit()

        input_file_name = sys.argv[1]
        USER_NAME = sys.argv[2]
        PASSWORD = sys.argv[3]
        try:
            SHOW_BROWSER = True if sys.argv[4] == '1' else False
        except IndexError as error:
            SHOW_BROWSER = False

    currentDT = datetime.datetime.now()

    login(USER_NAME, PASSWORD, SHOW_BROWSER)
    
    try:
        if os.path.isdir(input_file_name):
            files = os.listdir(input_file_name)
            for file_name in files:
                input_file = os.path.join(input_file_name, file_name)
                write_log("generated {0} links from input file {1}".format(run(input_file), input_file), log_filename)
        else:
            write_log("generated {0} links from input file {1}".format(run(input_file_name), input_file_name), log_filename)
    except Exception as exception:
        traceback.print_exc()
    finally:
        session.driver.quit()