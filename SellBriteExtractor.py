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
currentDT = None
currentDT_str = None


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
    connection = pymysql.connect(host='hatandbeyond-inven.ckocudrb3cns.us-west-1.rds.amazonaws.com',
                             user='HatAndBeyond',
                             password='HatAndBeyond123!',
                             db='HDB',
                             connect_timeout=5,
                             charset='utf8',
                             cursorclass=pymysql.cursors.DictCursor)

    write_log('MySql DB connection success!.', log_filename)
    return connection


def extract_inventory(inventory_dic, image_dic):
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
            "PRODUCT_SUPPLIER": product["brand"],
            "PRODUCT_NAME": product["name"],
            "PRODUCT_SIZE": None,
            "PRODUCT_COLOR": None,
            "PRODUCT_DESIGN": None,
            "PRODUCT_QTY": 0,
            "PRODUCT_PRICE": product["price"],
            "ID": product["id"],
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
                images.append({ "SKU": product["sku"], "IMAGE_PATH": img_link, "IMAGE_SOURCE": 1 })

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
                    "PRODUCT_SUPPLIER": variation["brand"],
                    "PRODUCT_NAME": variation["name"],
                    "PRODUCT_SIZE": variation["variation_fields"]["Size"] if "Size" in variation["variation_fields"] else None,
                    "PRODUCT_COLOR": variation["variation_fields"]["Color"] if "Color" in variation["variation_fields"] else None,
                    "PRODUCT_DESIGN": variation["variation_fields"]["Designs"] if "Designs" in variation["variation_fields"] else None,
                    "PRODUCT_QTY": 0 if variation["inventory"] == None else variation["inventory"],
                    "PRODUCT_PRICE": variation["price"],
                    "ID": variation["id"],
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
                        images.append({ "SKU": variation["sku"], "IMAGE_PATH": img_link, "IMAGE_SOURCE": 1 })

                cnt = cnt + 1
            
            if int(res["product"]["variation_count"]) == cnt:
                break

            break
        break

    res = { 'PRODUCTS': [], 'IMAGES': [], 'IDS': ids}
    for product in products:
        key_str = product['STD_SKU'] + '#'
        if key_str not in inventory_dic:
            res['PRODUCTS'].append(product)
            continue

        is_same = True
        for attribute in product:
            if 'ID' == attribute:
                continue

            if product[attribute] != inventory_dic[key_str][attribute]:
                res['PRODUCTS'].append(product)
                break

    for image in images:
        key_str = ''
        for key in ['SKU', 'IMAGE_PATH']:
            key_str = key_str + str(image[key]) + '#'

        if key_str not in image_dic:
            res['IMAGES'].append(image)
            continue

        for attribute in image:
            if image[attribute] != image_dic[key_str][attribute]:
                res['IMAGES'].append(image)
                break

    return res


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
    else:
        product['LISTING_PRODUCT_QTY'] = int(product['LISTING_PRODUCT_QTY'])

    if 0 == len(product['LISTING_PRODUCT_PRICE']):
        product['LISTING_PRODUCT_PRICE'] = 0.0
    else:
        product['LISTING_PRODUCT_PRICE'] = float(product['LISTING_PRODUCT_PRICE'])

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
    else:
        product['LISTING_PRODUCT_QTY'] = int(product['LISTING_PRODUCT_QTY'])

    if 0 == len(product['LISTING_PRODUCT_PRICE']):
        product['LISTING_PRODUCT_PRICE'] = 0.0
    else:
        product['LISTING_PRODUCT_PRICE'] = float(product['LISTING_PRODUCT_PRICE'])

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
    else:
        product['LISTING_PRODUCT_QTY'] = int(product['LISTING_PRODUCT_QTY'])

    if 0 == len(product['LISTING_PRODUCT_PRICE']):
        product['LISTING_PRODUCT_PRICE'] = 0.0
    else:
        product['LISTING_PRODUCT_PRICE'] = float(product['LISTING_PRODUCT_PRICE'])

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
    else:
        product['LISTING_PRODUCT_QTY'] = int(product['LISTING_PRODUCT_QTY'])

    if 0 == len(product['LISTING_PRODUCT_PRICE']):
        product['LISTING_PRODUCT_PRICE'] = 0.0
    else:
        product['LISTING_PRODUCT_PRICE'] = float(product['LISTING_PRODUCT_PRICE'])

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
        "LISTING_PRODUCT_PRICE": 0.0,
    }

    if 0 == len(product['LISTING_PRODUCT_QTY']):
        product['LISTING_PRODUCT_QTY'] = 0
    else:
        product['LISTING_PRODUCT_QTY'] = int(product['LISTING_PRODUCT_QTY'])

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


def extract_listing(ids, market, listing_dic, unlinked_listing_dic):
    linked_products = []
    unlinked_products = []
    pageNum = 0

    while True:
        try:
            items = []

            pageNum = pageNum + 1
            listing_url = 'https://app.sellbrite.com/channels/{0}?page={1}&status=Active'.format(market['SELLBRITE_LISTING_MARKET_ID'], pageNum)
            response = session.get(listing_url)
            soup = BeautifulSoup(response.text, 'html.parser')

            if market['CHANNEL_NAME'].lower() == 'shopify':
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
            elif market['CHANNEL_NAME'].lower() == 'ebay':
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
            elif market['CHANNEL_NAME'].lower() == 'walmart':
                items = soup.find('table', class_='slickgrid-table').find('tbody').find_all('tr')
                for item in items:
                    product, isLinked = extract_Walmart_listing_product_from_tr_ele(item, ids)
                    product["MARKET_ID"] = market['MARKET_ID']

                    if isLinked:
                        linked_products.append(product)
                    else:
                        unlinked_products.append(product)
            elif market['CHANNEL_NAME'].lower() == 'amazon':
                items = soup.find('table', class_='slickgrid-table').find('tbody').find_all('tr')
                for item in items:
                    product, isLinked = extract_Amazon_listing_product_from_tr_ele(item, ids)
                    product["MARKET_ID"] = market['MARKET_ID']

                    if isLinked:
                        linked_products.append(product)
                    else:
                        unlinked_products.append(product)
            elif market['CHANNEL_NAME'].lower() == 'sears':
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
            break
            
        except Exception as exception:
            traceback.print_exc()

    res = { 'LISTING': [], 'UNLINK_LISTING': [] }
    for item in linked_products:
        key_str = ''
        for key in ['LISTING_ITEM_ID', 'STD_SKU', 'MARKET_ID']:
            key_str = key_str + str(item[key]) + '#'

        if key_str not in listing_dic:
            res['LISTING'].append(item)
            continue

        for attribute in item:
            if str(item[attribute]) != str(listing_dic[key_str][attribute]):
                res['LISTING'].append(item)
                break

    for item in unlinked_products:
        key_str = ''
        for key in ['LISTING_ITEM_ID', 'MARKET_ID']:
            key_str = key_str + str(item[key]) + '#'

        if key_str not in unlinked_listing_dic:
            res['UNLINK_LISTING'].append(item)
            continue

        for attribute in item:
            if str(item[attribute]) != str(unlinked_listing_dic[key_str][attribute]):
                res['UNLINK_LISTING'].append(item)
                break

    return res


def retrieve_market_from_db(conn):
    market_data = []
    with conn.cursor() as cursor:
        # Read a single record
        sql = "SELECT `MARKET_ID`\
                    , `CHANNEL_NAME`\
                    , `BRAND_NAME`\
                    , `SELLBRITE_LISTING_MARKET_ID`\
                 FROM `MARKET`"
        cursor.execute(sql, ())
        market_meta = cursor.fetchall()
    return market_meta


def update_inventory_to_db(inventory, conn):
    conn.begin()
    with conn.cursor() as cursor:
        for product in inventory:
            if 0 < len(product['STD_SKU']):
                try:
                    sql = "INSERT INTO `INVENTORY` (\
                                  `STD_SKU`\
                                , `PARENT_STD_SKU`\
                                , `PRODUCT_SUPPLIER`\
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
                        product['PRODUCT_SUPPLIER'], \
                        product['PRODUCT_NAME'], \
                        product['PRODUCT_SIZE'], \
                        product['PRODUCT_COLOR'], \
                        product['PRODUCT_DESIGN'], \
                        product['PRODUCT_QTY'], \
                        product['PRODUCT_PRICE']))
                except pymysql.IntegrityError as error:
                    sql = "UPDATE `INVENTORY`\
                              SET `PARENT_STD_SKU`   = %s\
                                , `PRODUCT_SUPPLIER` = %s\
                                , `PRODUCT_NAME`     = %s\
                                , `PRODUCT_SIZE`     = %s\
                                , `PRODUCT_COLOR`    = %s\
                                , `PRODUCT_DESIGN`   = %s\
                                , `PRODUCT_QTY`      = %s\
                                , `PRODUCT_PRICE`    = %s\
                            WHERE `STD_SKU`          = %s"
                    cursor.execute(sql, ( \
                        product['PARENT_STD_SKU'], \
                        product['PRODUCT_SUPPLIER'], \
                        product['PRODUCT_NAME'], \
                        product['PRODUCT_SIZE'], \
                        product['PRODUCT_COLOR'], \
                        product['PRODUCT_DESIGN'], \
                        product['PRODUCT_QTY'], \
                        product['PRODUCT_PRICE'], \
                        product['STD_SKU']))
        conn.commit()
        cursor.close()


def retrieve_inventory_from_db(conn):
    inventory_data = []
    with conn.cursor() as cursor:
        sql = "SELECT `STD_SKU`\
                    , `PARENT_STD_SKU`\
                    , `PRODUCT_SUPPLIER`\
                    , `PRODUCT_NAME`\
                    , `PRODUCT_SIZE`\
                    , `PRODUCT_COLOR`\
                    , `PRODUCT_DESIGN`\
                    , `PRODUCT_QTY`\
                    , `PRODUCT_PRICE`\
                FROM `INVENTORY`"
        cursor.execute(sql, ())
        inventory_data = cursor.fetchall()
    return inventory_data


def update_images_to_db(images, conn):
    conn.begin()
    with conn.cursor() as cursor:
        for image in images:
            try:
                sql = "INSERT INTO `IMAGE` (\
                              `IMAGE_ID`\
                            , `SKU`\
                            , `IMAGE_PATH`\
                            , `IMAGE_SOURCE`\
                     ) VALUES (\
                              (SELECT `IMAGE_ID`\
                                 FROM (SELECT IFNULL(MAX(`IMAGE_ID`), 0) + 1 AS `IMAGE_ID`\
                                         FROM `IMAGE`) AS `MAX_ID`)\
                            , %s\
                            , %s\
                            , %s)"
                cursor.execute(sql, (\
                    image['SKU'], \
                    image['IMAGE_PATH'], \
                    image['IMAGE_SOURCE']))
            except pymysql.IntegrityError as error:
                print(error)
        conn.commit()
        cursor.close()


def retrieve_image_from_db(conn):
    image_data = []
    with conn.cursor() as cursor:
        sql = "SELECT `IMAGE_ID`\
                    , `SKU`\
                    , `IMAGE_PATH`\
                    , `IMAGE_SOURCE`\
                FROM `IMAGE`"
        cursor.execute(sql, ())
        image_data = cursor.fetchall()
    return image_data


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
                              SET `LISTING_SKU`           = %s\
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


def retrieve_listing_from_db(conn, market_id):
    listing_data = []
    with conn.cursor() as cursor:
        sql = "SELECT `LISTING_ITEM_ID`\
                    , `STD_SKU`\
                    , `MARKET_ID`\
                    , `LISTING_SKU`\
                    , `LISTING_PRODUCT_NAME`\
                    , `LISTING_PRODUCT_QTY`\
                    , `LISTING_PRODUCT_PRICE`\
                    , `LISTING_PRODUCT_FBM`\
                 FROM `LISTING`\
                WHERE `MARKET_ID` = %s"
        cursor.execute(sql, (market_id))
        listing_data = cursor.fetchall()
    return listing_data


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


def retrieve_unlink_listing_from_db(conn, market_id):
    unlink_listing_data = []
    with conn.cursor() as cursor:
        sql = "SELECT `LISTING_ITEM_ID`\
                    , `MARKET_ID`\
                    , `LISTING_SKU`\
                    , `LISTING_PRODUCT_NAME`\
                    , `LISTING_PRODUCT_QTY`\
                    , `LISTING_PRODUCT_PRICE`\
                    , `LISTING_PRODUCT_FBM`\
                 FROM `UNLINK_LISTING`\
                WHERE `MARKET_ID` = %s"
        cursor.execute(sql, (market_id))
        unlink_listing_data = cursor.fetchall()
    return unlink_listing_data


def list_to_dic(keys, data):
    dic = {}
    for item in data:
        key_str = ''
        for key in keys:
            key_str = key_str + str(item[key]) + '#'
        dic[key_str] = item
    return dic


def list_to_list_dic(keys, data):
    dic = {}
    for item in data:
        key_str = ''
        for key in keys:
            key_str = key_str + str(item[key]) + '#'

        if key_str not in dic:
            dic[key_str] = []
        
        dic[key_str].append(item)
        

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


def run():
    try:
        conn = openConnection()
        market_data = retrieve_market_from_db(conn)
        inventory_dic = list_to_dic(['STD_SKU'], retrieve_inventory_from_db(conn))
        image_dic = list_to_dic(['SKU', 'IMAGE_PATH'], retrieve_image_from_db(conn))

        write_log('Extracting inventory data...', log_filename)
        prev_datetime = datetime.datetime.now()
        inventory_data = extract_inventory(inventory_dic, image_dic)
        write_log('Extracted {0} inventory data and {1} image data'.format(len(inventory_data['PRODUCTS']), len(inventory_data['IMAGES'])), log_filename)
        write_log('Duration time: {0}'.format(datetime.datetime.now()-prev_datetime), log_filename)
        if 0 < len(inventory_data['PRODUCTS']):
            write_log('Update inventory data to DB...', log_filename)
            update_inventory_to_db(inventory_data['PRODUCTS'], conn)
            write_log(str(inventory_data['PRODUCTS']), log_filename)

        #     with open('inventory_products.{0}.csv'.format(currentDT_str), 'w', newline='', encoding='UTF8') as csvfile:
        #         fieldnames = list(inventory_data['PRODUCTS'][0].keys())
        #         writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        #         writer.writeheader()
        #         for product in inventory_data['PRODUCTS']:
        #             writer.writerow(product)

        if 0 < len(inventory_data['IMAGES']):
            write_log('Update image data to DB...', log_filename)
            update_images_to_db(inventory_data['IMAGES'], conn)
            write_log(str(inventory_data['IMAGES']), log_filename)
        #     with open('images.{0}.csv'.format(currentDT_str), 'w', newline='', encoding='UTF8') as csvfile:
        #         fieldnames = list(inventory_data['IMAGES'][0].keys())
        #         writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        #         writer.writeheader()
        #         for img in inventory_data['IMAGES']:
        #             writer.writerow(img)

        for market in market_data:
            listing_dic = list_to_dic(['LISTING_ITEM_ID', 'STD_SKU', 'MARKET_ID'], retrieve_listing_from_db(conn, market['MARKET_ID']))
            unlink_listing_dic = list_to_dic(['LISTING_ITEM_ID', 'MARKET_ID'], retrieve_unlink_listing_from_db(conn, market['MARKET_ID']))

            prev_datetime = datetime.datetime.now()
            write_log("Extracting listing data of {0} from {1}...".format(market['CHANNEL_NAME'], market['BRAND_NAME']), log_filename)
            listing_data = extract_listing(inventory_data['IDS'], market, listing_dic, unlink_listing_dic)
            write_log('Extracted {0} listing data and {1} unlinked listing data'.format(len(listing_data['LISTING']), len(listing_data['UNLINK_LISTING'])), log_filename)
            write_log('Duration time: {0}'.format(datetime.datetime.now()-prev_datetime), log_filename)
            if 0 < len(listing_data['LISTING']):
                write_log("Update listing data of {0} from {1} to DB...".format(market['CHANNEL_NAME'], market['BRAND_NAME']), log_filename)
                update_listing_to_db(listing_data['LISTING'], conn)
                write_log(str(listing_data['LISTING']), log_filename)
                
            #     with open('linked_listing.{0}.{1}.{2}.csv'.format(market['CHANNEL_NM'], market['BRAND_NM'], currentDT.strftime("%Y%m%d_%H%M%S")), 'w', newline='', encoding='UTF8') as csvfile:
            #         fieldnames = list(listing_data['LISTING'][0].keys())
            #         writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            #         writer.writeheader()
            #         for listing in listing_data['LISTING']:
            #             writer.writerow(listing)
            
            if 0 < len(listing_data['UNLINK_LISTING']):
                write_log("Update unlinked listing data of {0} from {1} to DB...".format(market['CHANNEL_NAME'], market['BRAND_NAME']), log_filename)
                update_unlink_listing_to_db(listing_data['UNLINK_LISTING'], conn)
                write_log(str(listing_data['UNLINK_LISTING']), log_filename)
            #     with open('unlinked_listing.{0}.{1}.{2}.csv'.format(market['CHANNEL_NM'], market['BRAND_NM'], currentDT.strftime("%Y%m%d_%H%M%S")), 'w', newline='', encoding='UTF8') as csvfile:
            #         fieldnames = list(listing_data['UNLINK_LISTING'][0].keys())
            #         writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            #         writer.writeheader()
            #         for listing in listing_data['UNLINK_LISTING']:
            #             writer.writerow(listing)
            
    except FileNotFoundError as error:
        write_log('{0}: {1}'.format(error.filename, error.strerror), log_filename)
    finally:
        conn.close()
    

if __name__ == '__main__':
    USER_NAME = ''
    PASSWORD = ''
    SHOW_BROWSER = False

    TEST = 0

    if TEST != 1:
        if len(sys.argv) < 3:
            print('Usage: python SellBriteExtractor.py [USER_ID] [PASSWORD] [0/1:SHOW_BROWSER]')
            exit()

        USER_NAME = sys.argv[1]
        PASSWORD = sys.argv[2]
        try:
            SHOW_BROWSER = True if sys.argv[3] == '1' else False
        except IndexError as error:
            SHOW_BROWSER = False

    login(USER_NAME, PASSWORD, SHOW_BROWSER)
    currentDT = datetime.datetime.now()
    currentDT_str = currentDT.strftime("%Y%m%d_%H%M%S")

    log_filename = './log/SellBriteExtractor_{0}.log'.format(currentDT_str)
    print("Log file name: {0}".format(log_filename))

    write_log("Start SellBrite Extraction on {0}".format(currentDT), log_filename)
    
    try:
        run()
    except Exception as exception:
        traceback.print_exc()
    finally:
        session.driver.quit()

    write_log("Finish SellBrite Extraction on {0}".format(datetime.datetime.now()), log_filename)
    write_log("Total Duration Time: {0}".format(datetime.datetime.now()-currentDT), log_filename)
    
