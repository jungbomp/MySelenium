from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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

import pymysql.cursors


session = None
log_filename = None
result_filename = None


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

    session.driver.get(('https://app.sellbrite.com/merchants/sign_in'))

    username = session.driver.find_element_by_id('user_email')
    username.send_keys(username_str)
    password = session.driver.find_element_by_id('user_password')
    password.send_keys(password_str)
    nextButton = session.driver.find_element_by_id('clickme')
    nextButton.click()

    session.transfer_driver_cookies_to_session();
    bLogin = True
    return bLogin


def openConnection():
    connection = pymysql.connect(host='localhost',
                             user='app',
                             password='HatAndBeyond123!',
                             db='hdb',
                             connect_timeout=5,
                             charset='utf8',
                             cursorclass=pymysql.cursors.DictCursor)
    return connection


def extract_inventory():
    all_product = []

    page = 0
    while True:
        page = page + 1
        response = session.get('https://app.sellbrite.com/products?advancedOptions=false&page={0}&page_size=100'.format(page))
        # response = session.get('https://app.sellbrite.com/products?advancedOptions=false&page=1&page_size=100&query=M92Lqj4PVLgDAlyn')
        
        res = response.json()
        if len(res) == 0:
            break
        all_product = all_product + res

    if len(all_product) == 0:
        return

    ids = {}
    products = []
    images = []
    for i, product in enumerate(all_product):
        products.append({ "STD_SKU": product["sku"],
            "PARENT_STD_SKU": None,
            "PRODUCT_BRAND": product["brand"],
            "PRODUCT_NAME": product["name"],
            "PRODUCT_SIZE": None,
            "PRODUCT_COLOR": None,
            "PRODUCT_DESIGN": None,
            "PRODUCT_QTY": None,
            "PRODUCT_PRICE": product["price"],
            # "PRODUCT_DESCRIPTION": product["description"],
            # "PRODUCT_FEATURE1": product["features"][0] if 0 < len(product["features"]) else None,
            # "PRODUCT_FEATURE2": product["features"][1] if 1 < len(product["features"]) else None,
            # "PRODUCT_FEATURE3": product["features"][2] if 2 < len(product["features"]) else None,
            # "PRODUCT_FEATURE4": product["features"][3] if 3 < len(product["features"]) else None,
            # "PRODUCT_FEATURE5": product["features"][4] if 4 < len(product["features"]) else None 
            })
        
        ids[product["id"]] = product["sku"]

        if product["images"] != None:
            for j, img_link in enumerate(product["images"]):
                images.append({ "STD_SKU": product["sku"], "IMAGE_PATH": img_link })

        page = 0
        cnt = 0
        while True:
            page = page + 1
            response = session.get('https://app.sellbrite.com/products/{0}/product_variations?page={1}'.format(product["id"], page))
            res = response.json()
            if len(res["variations"]) < 1:
                break

            for variation in res["variations"]:
                products.append({ "STD_SKU": variation["sku"],
                    "PARENT_STD_SKU": product["sku"],
                    "PRODUCT_BRAND": variation["brand"],
                    "PRODUCT_NAME": variation["name"],
                    "PRODUCT_SIZE": variation["variation_fields"]["Size"] if "Size" in variation["variation_fields"] else None,
                    "PRODUCT_COLOR": variation["variation_fields"]["Color"] if "Color" in variation["variation_fields"] else None,
                    "PRODUCT_DESIGN": variation["variation_fields"]["Designs"] if "Designs" in variation["variation_fields"] else None,
                    "PRODUCT_QTY": variation["inventory"],
                    "PRODUCT_PRICE": variation["price"],
                    # "PRODUCT_DESCRIPTION": variation["description"],
                    # "PRODUCT_FEATURE1": variation["features"][0] if 0 < len(variation["features"]) else None,
                    # "PRODUCT_FEATURE2": variation["features"][1] if 1 < len(variation["features"]) else None,
                    # "PRODUCT_FEATURE3": variation["features"][2] if 2 < len(variation["features"]) else None,
                    # "PRODUCT_FEATURE4": variation["features"][3] if 3 < len(variation["features"]) else None,
                    # "PRODUCT_FEATURE5": variation["features"][4] if 4 < len(variation["features"]) else None
                    })

                ids[variation["id"]] = variation["sku"]
                
                if variation["images"] != None:
                    for j, img_link in enumerate(variation["images"]):
                        images.append({ "STD_SKU": variation["sku"], "IMAGE_PATH": img_link })

                cnt = cnt + 1
            
            if int(res["product"]["variation_count"]) == cnt:
                break

    return products, images, ids


def extract_shopify_listing_product_from_tr_ele(tr_ele, ids):
    product = {
        "LISTING_ITEM_ID": tr_ele.find('td', class_='LMT-table-sku').text.strip('\n '),
        "LISTING_SKU": tr_ele.find('td', class_='LMT-table-sku').text.strip('\n '),
        "LISTING_PRODUCT_QTY": tr_ele.find('td', attrs={"title":"Quantity"}).text.strip('\n '),
        "LISTING_PRODUCT_PRICE": tr_ele.find('td', attrs={"title":"Price"}).text.strip('\n $'),
        "LISTING_PRODUCT_FBM": 'Y'
    }

    if 0 == len(product['LISTING_PRODUCT_QTY']):
        product['LISTING_PRODUCT_QTY'] = 0

    if 0 == len(product['LISTING_PRODUCT_PRICE']):
        product['LISTING_PRODUCT_PRICE'] = 0

    if tr_ele.find('div', class_='linked-icon') != None:
        linkstr = tr_ele.find('a', class_='link').attrs['href']

        try:
            product["STD_SKU"] = ids[int(linkstr[linkstr.find('/', 2)+1:linkstr.rfind('/')])]
        except KeyError as error:
            response = session.get('https://app.sellbrite.com'+linkstr)
            soup = BeautifulSoup(response.text, 'html.parser')
            product["STD_SKU"] = soup.find('input', class_='form-control', attrs={'name': 'product[sku]'}).attrs['value']
            
        return product, True
    else:
        return product, False


def extract_ebay_listing_product_from_tr_ele(tr_ele, ids):
    product = {
        "LISTING_ITEM_ID": tr_ele.find('td', attrs={"data-key":"sku"}).text.strip('\n '),
        "LISTING_SKU": tr_ele.find('td', attrs={"data-key":"sku"}).text.strip('\n '),
        "LISTING_PRODUCT_NAME": tr_ele.find('td', attrs={"data-key":"title"}).find('a').text.strip('\n '),
        "LISTING_PRODUCT_QTY": tr_ele.find('td', attrs={"data-key":"quantity"}).text.strip('\n '),
        "LISTING_PRODUCT_PRICE": tr_ele.find('td', attrs={"data-key":"buy_it_now"}).text.strip('\n $'),
        "LISTING_PRODUCT_FBM": 'Y'
    }

    if 0 == len(product['LISTING_PRODUCT_QTY']):
        product['LISTING_PRODUCT_QTY'] = 0

    if 0 == len(product['LISTING_PRODUCT_PRICE']):
        product['LISTING_PRODUCT_PRICE'] = 0

    if tr_ele.find('td', attrs={'data-key': 'icon'}).find('div', class_='linked-icon') != None:
        linkstr = tr_ele.find('td', attrs={'data-key': 'icon'}).find('a', class_='link').attrs['href']
        
        try:
            product["STD_SKU"] = ids[int(linkstr[linkstr.find('/', 2)+1:linkstr.rfind('/')])]
        except KeyError as error:
            response = session.get('https://app.sellbrite.com'+linkstr)
            soup = BeautifulSoup(response.text, 'html.parser')
            product["STD_SKU"] = soup.find('input', class_='form-control', attrs={'name': 'product[sku]'}).attrs['value']
            
        return product, True
    else:
        return product, False


def extract_Walmart_listing_product_from_tr_ele(tr_ele, ids):
    product = {
        "LISTING_PRODUCT_NAME": tr_ele.find('td', attrs={"data-key":"title"}).find('a').text.strip('\n '),
        "LISTING_PRODUCT_QTY": tr_ele.find('td', attrs={"data-key":"quantity"}).text.strip('\n '),
        "LISTING_PRODUCT_PRICE": tr_ele.find('td', attrs={"data-key":"price"}).text.strip('\n $'),
    }

    if 0 == len(product['LISTING_PRODUCT_QTY']):
        product['LISTING_PRODUCT_QTY'] = 0

    if 0 == len(product['LISTING_PRODUCT_PRICE']):
        product['LISTING_PRODUCT_PRICE'] = 0

    product["LISTING_ITEM_ID"] = tr_ele.find('td', attrs={'data-key': 'listing_ref'}).text.strip('\n ')
    product["LISTING_SKU"] = tr_ele.find('td', attrs={'data-key': 'sku'}).text.strip('\n ')
    product["LISTING_PRODUCT_FBM"] = 'Y'

    if tr_ele.find('td', attrs={'data-key': 'icon'}).find('div', class_='linked-icon') != None:
        linkstr = tr_ele.find('td', attrs={'data-key': 'icon'}).find('a', class_='link').attrs['href']
        
        try:
            product["STD_SKU"] = ids[int(linkstr[linkstr.find('/', 2)+1:linkstr.rfind('/')])]
        except KeyError as error:
            response = session.get('https://app.sellbrite.com'+linkstr)
            soup = BeautifulSoup(response.text, 'html.parser')
            product["STD_SKU"] = soup.find('input', class_='form-control', attrs={'name': 'product[sku]'}).attrs['value']
            
        return product, True
    else:
        return product, False


def extract_Amazon_listing_product_from_tr_ele(tr_ele, ids):
    product = {
        "LISTING_PRODUCT_NAME": tr_ele.find('td', attrs={"data-key":"title"}).find('a').text.strip('\n '),
        "LISTING_PRODUCT_QTY": tr_ele.find('td', attrs={"data-key":"quantity"}).text.strip('\n '),
        "LISTING_PRODUCT_PRICE": tr_ele.find('td', attrs={"data-key":"price"}).text.strip('\n $'),
    }

    if 0 == len(product['LISTING_PRODUCT_QTY']):
        product['LISTING_PRODUCT_QTY'] = 0

    if 0 == len(product['LISTING_PRODUCT_PRICE']):
        product['LISTING_PRODUCT_PRICE'] = 0

    product["LISTING_ITEM_ID"] = tr_ele.find('td', attrs={'data-key': 'item_id'}).text.strip('\n ')
    product["LISTING_SKU"] = tr_ele.find('td', attrs={'data-key': 'sku'}).text.strip('\n ')
    product["LISTING_PRODUCT_FBM"] = 'Y' if tr_ele.find('td', attrs={'data-key':'fulfilled_by'}).text.strip('\n ').lower() == 'merchant' else 'N'
    
    if tr_ele.find('td', attrs={'data-key': 'icon'}).find('div', class_='linked-icon') != None:
        linkstr = tr_ele.find('td', attrs={'data-key': 'icon'}).find('a', class_='link').attrs['href']
        
        try:
            product["STD_SKU"] = ids[int(linkstr[linkstr.find('/', 2)+1:linkstr.rfind('/')])]
        except KeyError as error:
            response = session.get('https://app.sellbrite.com'+linkstr)
            soup = BeautifulSoup(response.text, 'html.parser')
            product["STD_SKU"] = soup.find('input', class_='form-control', attrs={'name': 'product[sku]'}).attrs['value']
            
        return product, True
    else:
        return product, False


def extract_Sears_listing_product_from_tr_ele(tr_ele, ids):
    product = {
        "LISTING_PRODUCT_NAME": tr_ele.find('td', class_='LMT-table-title').text.strip('\n '),
        "LISTING_PRODUCT_QTY": tr_ele.find('td', attrs={"title":"Available Quantity"}).find('span').text.strip('\n '),
        "LISTING_PRODUCT_PRICE": 0,
    }

    if 0 == len(product['LISTING_PRODUCT_QTY']):
        product['LISTING_PRODUCT_QTY'] = 0

    product["LISTING_ITEM_ID"] = tr_ele.find('td', class_='LMT-table-sku').text.strip('\n ')
    product["LISTING_SKU"] = tr_ele.find('td', class_='LMT-table-sku').text.strip('\n ')
    product["LISTING_PRODUCT_FBM"] = 'Y'
    
    if tr_ele.find('td', class_='product-popover').find('div', class_='linked-icon') != None:
        linkstr = tr_ele.find('td', class_='product-popover').find('a', class_='link').attrs['href']
        
        try:
            product["STD_SKU"] = ids[int(linkstr[linkstr.find('/', 2)+1:linkstr.rfind('/')])]
        except KeyError as error:
            response = session.get('https://app.sellbrite.com'+linkstr)
            soup = BeautifulSoup(response.text, 'html.parser')
            product["STD_SKU"] = soup.find('input', class_='form-control', attrs={'name': 'product[sku]'}).attrs['value']
            
        return product, True
    else:
        return product, False


def extract_listing(ids, market):
    linked_products = []
    unlinked_products = []
    pageNum = 0

    while True:
        try:
            items = []

            pageNum = pageNum + 1
            listing_url = 'https://app.sellbrite.com/channels/{0}?page={1}&status=Active'.format(market['LISTING_MARKET_ID'], pageNum)
            response = session.get(listing_url)
            soup = BeautifulSoup(response.text, 'html.parser')

            if market['CHANNEL_NM'].lower() == 'shopify':
                items = soup.find('table', class_='LMT-table').find('tbody').find_all('tr')
                product_name = ''
                for item in items:
                    if item.attrs['class'][0] == 'LMT-listing-row':
                        product_name = item.find('td', class_='LMT-table-title').find('a').text.strip('\n ')
                        continue

                    product, isLinked = extract_shopify_listing_product_from_tr_ele(item, ids)
                    product["LISTING_PRODUCT_NAME"] = product_name
                    product["MARKET_ID"] = market['MARKET_ID']

                    if isLinked:
                        linked_products.append(product)
                    else:
                        unlinked_products.append(product)
            elif market['CHANNEL_NM'].lower() == 'ebay':
                items = soup.find('table', class_='slickgrid-table').find('tbody').find_all('tr')
                parent = None
                for i in range(len(items)-1, -1, -1):
                    item = items[i]
                    data_key = json.loads(item['data-key'])
                    if 'id' in data_key and data_key['id'] == parent:
                        parent = None
                        continue

                    parent = data_key['parent']
                    product, isLinked = extract_ebay_listing_product_from_tr_ele(item, ids)
                    product["MARKET_ID"] = market['MARKET_ID']

                    if isLinked:
                        linked_products.append(product)
                    else:
                        unlinked_products.append(product)
            elif market['CHANNEL_NM'].lower() == 'walmart':
                items = soup.find('table', class_='slickgrid-table').find('tbody').find_all('tr')
                for item in items:
                    product, isLinked = extract_Walmart_listing_product_from_tr_ele(item, ids)
                    product["MARKET_ID"] = market['MARKET_ID']

                    if isLinked:
                        linked_products.append(product)
                    else:
                        unlinked_products.append(product)
            elif market['CHANNEL_NM'].lower() == 'amazon':
                items = soup.find('table', class_='slickgrid-table').find('tbody').find_all('tr')
                for item in items:
                    product, isLinked = extract_Amazon_listing_product_from_tr_ele(item, ids)
                    product["MARKET_ID"] = market['MARKET_ID']

                    if isLinked:
                        linked_products.append(product)
                    else:
                        unlinked_products.append(product)
            elif market['CHANNEL_NM'].lower() == 'sears':
                items = soup.find('table', class_='LMT-table').find('tbody').find_all('tr')
                for item in items:
                    product, isLinked = extract_Sears_listing_product_from_tr_ele(item, ids)
                    product["MARKET_ID"] = market['MARKET_ID']

                    if isLinked:
                        linked_products.append(product)
                    else:
                        unlinked_products.append(product)

            if len(items) < 1:
                break
            
        except Exception as exception:
            traceback.print_exc()

    return linked_products, unlinked_products


def update_inventory_to_db(inventory, conn):
    conn.begin()
    with conn.cursor() as cursor:
        for product in inventory:
            if 0 < len(product['STD_SKU']):
                try:
                    sql = "INSERT INTO `INVENTORY` (\
                                  `STD_SKU`\
                                , `PARENT_STD_SKU`\
                                , `PRODUCT_BRAND`\
                                , `PRODUCT_NAME`\
                                , `PRODUCT_SIZE`\
                                , `PRODUCT_COLOR`\
                                , `PRODUCT_DESIGN`\
                                , `PRODUCT_QTY`\
                                , `PRODUCT_PRICE`\
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    cursor.execute(sql, (\
                        product['STD_SKU'], \
                        product['PARENT_STD_SKU'], \
                        product['PRODUCT_BRAND'], \
                        product['PRODUCT_NAME'], \
                        product['PRODUCT_SIZE'], \
                        product['PRODUCT_COLOR'], \
                        product['PRODUCT_DESIGN'], \
                        product['PRODUCT_QTY'], \
                        product['PRODUCT_PRICE']))
                except pymysql.IntegrityError as error:
                    sql = "UPDATE `INVENTORY`\
                            SET `PARENT_STD_SKU` = %s\
                                , `PRODUCT_BRAND`  = %s\
                                , `PRODUCT_NAME`   = %s\
                                , `PRODUCT_SIZE`   = %s\
                                , `PRODUCT_COLOR`  = %s\
                                , `PRODUCT_DESIGN` = %s\
                                , `PRODUCT_QTY`    = %s\
                                , `PRODUCT_PRICE`  = %s\
                            WHERE `STD_SKU`        = %s"
                    cursor.execute(sql, ( \
                        product['PARENT_STD_SKU'], \
                        product['PRODUCT_BRAND'], \
                        product['PRODUCT_NAME'], \
                        product['PRODUCT_SIZE'], \
                        product['PRODUCT_COLOR'], \
                        product['PRODUCT_DESIGN'], \
                        product['PRODUCT_QTY'], \
                        product['PRODUCT_PRICE'], \
                        product['STD_SKU']))
        conn.commit()
        cursor.close()


def update_images_to_db(images, conn):
    conn.begin()
    with conn.cursor() as cursor:
        for image in images:
            try:
                sql = "SELECT `IMAGE_ID`\
                         FROM `IMAGE`\
                        WHERE `SKU`          = %s\
                          AND `IMAGE_PATH`   = %s\
                          AND `IMAGE_SOURCE` = 1"
                cursor.execute(sql, (image['STD_SKU'], image['IMAGE_PATH']))
                image_id = cursor.fetchall()
                if 0 < len(image_id):
                    continue
                        
                sql = "INSERT INTO `IMAGE` (\
                              `IMAGE_ID`\
                            , `SKU`\
                            , `IMAGE_PATH`\
                            , `IMAGE_SOURCE`)\
                        VALUES (\
                                (SELECT `IMAGE_ID`\
                                    FROM (SELECT IFNULL(MAX(`IMAGE_ID`), 0) + 1 AS `IMAGE_ID`\
                                            FROM `IMAGE`) AS `MAX_ID`)\
                            , %s\
                            , %s\
                            , 1)"
                cursor.execute(sql, (\
                    image['STD_SKU'], \
                    image['IMAGE_PATH']))
            except pymysql.IntegrityError as error:
                print(error)
        conn.commit()
        cursor.close()


def update_listing_to_db(listing, conn):
    conn.begin()
    with conn.cursor() as cursor:
        for item in listing:
            if 0 < len(item['LISTING_SKU']) and 0 < len(item['STD_SKU']):
                try:
                    sql = "INSERT INTO `LISTING` (\
                                  `LISTING_ITEM_ID`\
                                , `STD_SKU`\
                                , `MARKET_ID`\
                                , `LISTING_SKU`\
                                , `LISTING_PRODUCT_NAME`\
                                , `LISTING_PRODUCT_QTY`\
                                , `LISTING_PRODUCT_PRICE`\
                                , `LISTING_PRODUCT_FBM`\
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                    cursor.execute(sql, (\
                        item['LISTING_ITEM_ID'], \
                        item['STD_SKU'], \
                        item['MARKET_ID'], \
                        item['LISTING_SKU'], \
                        item['LISTING_PRODUCT_NAME'], \
                        item['LISTING_PRODUCT_QTY'], \
                        item['LISTING_PRODUCT_PRICE'], \
                        item['LISTING_PRODUCT_FBM']))
                except pymysql.IntegrityError as error:
                    sql = "UPDATE `LISTING`\
                              SET `LISTING_SKU`           = %S\
                                , `LISTING_PRODUCT_NAME`  = %s\
                                , `LISTING_PRODUCT_QTY`   = %s\
                                , `LISTING_PRODUCT_PRICE` = %s\
                                , `LISTING_PRODUCT_FBM`   = %s\
                            WHERE `LISTING_ITEM_ID`       = %s\
                              AND `STD_SKU`               = %s\
                              AND `MARKET_ID`             = %s"
                    cursor.execute(sql, ( \
                        item['LISTING_SKU'], \
                        item['LISTING_PRODUCT_NAME'], \
                        item['LISTING_PRODUCT_QTY'], \
                        item['LISTING_PRODUCT_PRICE'], \
                        item['LISTING_PRODUCT_FBM'], \
                        item['LISTING_ITEM_ID'], \
                        item['STD_SKU'], \
                        item['MARKET_ID']))
        conn.commit()
        cursor.close()


def update_unlink_listing_to_db(listing, conn):
    conn.begin()
    with conn.cursor() as cursor:
        for item in listing:
            if 0 < len(item['LISTING_SKU']):
                try:
                    sql = "INSERT INTO `UNLINK_LISTING` (\
                                  `LISTING_ITEM_ID`\
                                , `MARKET_ID`\
                                , `LISTING_SKU`\
                                , `LISTING_PRODUCT_NAME`\
                                , `LISTING_PRODUCT_QTY`\
                                , `LISTING_PRODUCT_PRICE`\
                                , `LISTING_PRODUCT_FBM`\
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                    cursor.execute(sql, (\
                        item['LISTING_ITEM_ID'], \
                        item['MARKET_ID'], \
                        item['LISTING_SKU'], \
                        item['LISTING_PRODUCT_NAME'], \
                        item['LISTING_PRODUCT_QTY'], \
                        item['LISTING_PRODUCT_PRICE'], \
                        item['LISTING_PRODUCT_FBM']))
                except pymysql.IntegrityError as error:
                    sql = "UPDATE `UNLINK_LISTING`\
                              SET `LISTING_SKU`           = %s\
                                , `LISTING_PRODUCT_NAME`  = %s\
                                , `LISTING_PRODUCT_QTY`   = %s\
                                , `LISTING_PRODUCT_PRICE` = %s\
                                , `LISTING_PRODUCT_FBM`   = %s\
                            WHERE `LISTING_ITEM_ID`       = %s\
                              AND `MARKET_ID`             = %s"
                    cursor.execute(sql, ( \
                        item['LISTING_SKU'], \
                        item['LISTING_PRODUCT_NAME'], \
                        item['LISTING_PRODUCT_QTY'], \
                        item['LISTING_PRODUCT_PRICE'], \
                        item['LISTING_PRODUCT_FBM'], \
                        item['LISTING_ITEM_ID'], \
                        item['MARKET_ID']))
        conn.commit()
        cursor.close()
        

def write_log(msg, file_name):
    print(msg)
    with open(file_name, mode='a+') as log_file:
        log_file.write(msg+'\n')


def read_from_file():
    try:
        conn = openConnection()
        conn.begin()
        with conn.cursor() as cursor:
            filename = 'linked_listing.csv'
            with open(filename) as in_file:
                reader = csv.reader(in_file, delimiter=',')
                for i, item in enumerate(reader):
                    if 0 == i:
                        continue
                    
                    if 0 < len(item[0]) and 0 < len(item[1]):
                        try:
                            sql = "INSERT INTO `LISTING` (\
                                        `LISTING_SKU`\
                                        , `STD_SKU`\
                                        , `MARKET_ID`\
                                        , `LISTING_PRODUCT_NAME`\
                                        , `LISTING_PRODUCT_QTY`\
                                        , `LISTING_PRODUCT_PRICE`\
                                        , `LISTING_PRODUCT_FBM`\
                                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                            cursor.execute(sql, (\
                                item[0], \
                                item[1], \
                                item[2], \
                                item[3], \
                                item[4], \
                                0 if 0 == len(item[5].strip()) else item[5], \
                                item[6]))
                        except pymysql.IntegrityError as error:
                            sql = "UPDATE `LISTING`\
                                    SET `LISTING_PRODUCT_NAME`  = %s\
                                        , `LISTING_PRODUCT_QTY`   = %s\
                                        , `LISTING_PRODUCT_PRICE` = %s\
                                        , `LISTING_PRODUCT_FBM`   = %s\
                                    WHERE `LISTING_SKU`           = %s\
                                    AND `STD_SKU`               = %s\
                                    AND `MARKET_ID`             = %s"
                            cursor.execute(sql, ( \
                                item[3], \
                                item[4], \
                                0 if 0 == len(item[5].strip()) else item[5], \
                                item[6], \
                                item[0], \
                                item[1], \
                                item[2]))
                        except pymysql.DataError as error:
                            print(error)

            filename = 'unlinked_listing.csv'
            with open(filename) as in_file:
                reader = csv.reader(in_file, delimiter=',')
                for i, item in enumerate(reader):
                    if 0 == i:
                        continue
                    
                    if 0 < len(item[0]):
                        try:
                            sql = "INSERT INTO `UNLINK_LISTING` (\
                                          `LISTING_SKU`\
                                        , `MARKET_ID`\
                                        , `LISTING_PRODUCT_NAME`\
                                        , `LISTING_PRODUCT_QTY`\
                                        , `LISTING_PRODUCT_PRICE`\
                                        , `LISTING_PRODUCT_FBM`\
                                    ) VALUES (%s, %s, %s, %s, %s, %s)"
                            cursor.execute(sql, (\
                                item[0], \
                                item[1], \
                                item[2], \
                                item[3], \
                                item[4], \
                                item[5]))
                        except pymysql.IntegrityError as error:
                            sql = "UPDATE `UNLINK_LISTING`\
                                      SET `LISTING_PRODUCT_NAME`  = %s\
                                        , `LISTING_PRODUCT_QTY`   = %s\
                                        , `LISTING_PRODUCT_PRICE` = %s\
                                        , `LISTING_PRODUCT_FBM`   = %s\
                                    WHERE `LISTING_SKU`           = %s\
                                      AND `MARKET_ID`             = %s"
                            cursor.execute(sql, ( \
                                item[2], \
                                item[3], \
                                item[4], \
                                item[5], \
                                item[0], \
                                item[1]))

            conn.commit()
            cursor.close()
    except FileNotFoundError as error:
        write_log('{0}: {1}'.format(error.filename, error.strerror), log_filename)
    finally:
        conn.close()


def run(file_name):
    global log_filename
    global result_filename

    # log_filename = '{0}.{1}.log'.format(file_name.replace('.csv', ''), currentDT.strftime("%Y%m%d_%H%M%S"))
    
    result_filename = 'products.{1}.csv'.format('ret', currentDT.strftime("%Y%m%d_%H%M%S"))
    # print("Log file name: {0}".format(log_filename))
    print("Remain file name: {0}".format(result_filename))

    # write_log('Start with input file: {0}'.format(file_name), log_filename)
    
    linked_sku_cnt = 0

    try:
        conn = openConnection()
        with conn.cursor() as cursor:
            # Read a single record
            sql = "SELECT `MARKET_ID`, `CHANNEL_NM`, `BRAND_NM`, `LISTING_MARKET_ID` FROM `MARKET`"
            cursor.execute(sql, ())
            market_meta = cursor.fetchall()

        products, images, ids = extract_inventory()
        if 0 < len(products):
            update_inventory_to_db(products, conn)
            update_images_to_db(images, conn)

            with open('inventory_products.{0}.csv'.format(currentDT.strftime("%Y%m%d_%H%M%S")), 'w', newline='', encoding='UTF8') as csvfile:
                fieldnames = list(products[0].keys())
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for product in products:
                    writer.writerow(product)

            with open('images.{0}.csv'.format(currentDT.strftime("%Y%m%d_%H%M%S")), 'w', newline='', encoding='UTF8') as csvfile:
                fieldnames = ['STD_SKU', 'IMAGE_PATH']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                for img in images:
                    writer.writerow(img)

            for market in market_meta:
                # if market['LISTING_MARKET_ID'] == 62179:
                #     continue
                if market['MARKET_ID'] in [8]:
                    continue
                linked_listing, unlinked_listing = extract_listing(ids, market)
                if 0 < len(linked_listing):
                    update_listing_to_db(linked_listing, conn)

                    with open('linked_listing.{0}.{1}.{2}.csv'.format(market['CHANNEL_NM'], market['BRAND_NM'], currentDT.strftime("%Y%m%d_%H%M%S")), 'w', newline='', encoding='UTF8') as csvfile:
                        fieldnames = list(linked_listing[0].keys())
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                        writer.writeheader()
                        for listing in linked_listing:
                            writer.writerow(listing)
                
                if 0 < len(unlinked_listing):
                    update_unlink_listing_to_db(unlinked_listing, conn)

                    with open('unlinked_listing.{0}.{1}.{2}.csv'.format(market['CHANNEL_NM'], market['BRAND_NM'], currentDT.strftime("%Y%m%d_%H%M%S")), 'w', newline='', encoding='UTF8') as csvfile:
                        fieldnames = list(unlinked_listing[0].keys())
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                        writer.writeheader()
                        for listing in unlinked_listing:
                            writer.writerow(listing)
    except FileNotFoundError as error:
        write_log('{0}: {1}'.format(error.filename, error.strerror), log_filename)
    finally:
        conn.close()
    
    return linked_sku_cnt


if __name__ == '__main__':
    # read_from_file()
    USER_NAME = 'jungbomp@usc.edu'
    PASSWORD = 'asdf1231003'
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
