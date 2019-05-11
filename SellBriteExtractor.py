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


session = None
log_filename = None
result_filename = None

meta = {
    'amazon': {
        'hab': 56358,
        'mx': 56020,
        'url': 'https://app.sellbrite.com/channels/{0}?action=filter&channel_id={0}&controller=listings&fb_merchant=true&max_price=&min_price=&query={1}&status=&template_id=&utf8=%E2%9C%93'
    },
    'walmart': {
        'hab': 60834,
        'mx': 56021,
        'url': 'https://app.sellbrite.com/channels/{0}?action=filter&channel_id={0}&controller=listings&max_price=&min_price=&query={1}&status=&template_id=&utf8=%E2%9C%93'
    },
    'sku_url': 'https://app.sellbrite.com/inventories/by_product?page=1&page_size=100&query={0}&status=available&with_tag_ids=',
}


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

def extract_inventory():
    all_product = []

    page = 1
    while True:
        response = session.get('https://app.sellbrite.com/products?advancedOptions=false&page={0}&page_size=100'.format(page))
        res = response.json()
        if len(res) == 0:
            break
        all_product = all_product + res
        page = page + 1

    if len(all_product) == 0:
        return

    products = []
    images = []
    for i, product in enumerate(all_product):
        products.append({ "STD_SKU": product["sku"],
            "PARENT_STD_SKU": None,
            "PRODUCT_BRAND": product["brand"],
            "PRODUCT_NAME": product["name"],
            "PRODUCT_SIZE": None,
            "PRODUCT_COLOR": None,
            "PRODUCT_DESIGNS": None,
            "PRODUCT_QTY": None,
            "PRODUCT_PRICE": product["price"],
            "PRODUCT_DESCRIPTION": product["description"],
            "PRODUCT_FEATURE1": product["features"][0] if 0 < len(product["features"]) else None,
            "PRODUCT_FEATURE2": product["features"][1] if 1 < len(product["features"]) else None,
            "PRODUCT_FEATURE3": product["features"][2] if 2 < len(product["features"]) else None,
            "PRODUCT_FEATURE4": product["features"][3] if 3 < len(product["features"]) else None,
            "PRODUCT_FEATURE5": product["features"][4] if 4 < len(product["features"]) else None })

        if product["images"] != None:
            for j, img_link in enumerate(product["images"]):
                images.append({ "STD_SKU": product["sku"], "IMAGE_PATH": img_link })

        response = session.get('https://app.sellbrite.com/products/{}/product_variations'.format(product["id"]))
        res = response.json()
        for variation in res["variations"]:
            products.append({ "STD_SKU": variation["sku"],
                "PARENT_STD_SKU": product["sku"],
                "PRODUCT_BRAND": variation["brand"],
                "PRODUCT_NAME": variation["name"],
                "PRODUCT_SIZE": variation["variation_fields"]["Size"] if "Size" in variation["variation_fields"] else None,
                "PRODUCT_COLOR": variation["variation_fields"]["Color"] if "Color" in variation["variation_fields"] else None,
                "PRODUCT_DESIGNS": variation["variation_fields"]["Designs"] if "Designs" in variation["variation_fields"] else None,
                "PRODUCT_QTY": variation["inventory"],
                "PRODUCT_PRICE": variation["price"],
                "PRODUCT_DESCRIPTION": variation["description"],
                "PRODUCT_FEATURE1": variation["features"][0] if 0 < len(variation["features"]) else None,
                "PRODUCT_FEATURE2": variation["features"][1] if 1 < len(variation["features"]) else None,
                "PRODUCT_FEATURE3": variation["features"][2] if 2 < len(variation["features"]) else None,
                "PRODUCT_FEATURE4": variation["features"][3] if 3 < len(variation["features"]) else None,
                "PRODUCT_FEATURE5": variation["features"][4] if 4 < len(variation["features"]) else None })

            if variation["images"] != None:
                for j, img_link in enumerate(variation["images"]):
                    images.append({ "STD_SKU": variation["sku"], "IMAGE_PATH": img_link })

    with open('inventory_products.{1}.csv'.format(currentDT.strftime("%Y%m%d_%H%M%S")), 'w', newline='') as csvfile:
        fieldnames = list(products[0].keys())
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for product in products:
            writer.writerow(product)

    with open('images.{1}.csv'.format(currentDT.strftime("%Y%m%d_%H%M%S")), 'w', newline='') as csvfile:
        fieldnames = ['STD_SKU', 'IMAGE_PATH']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for img in images:
            writer.writerow(img)


def write_log(msg, file_name):
    print(msg)
    with open(file_name, mode='a+') as log_file:
        log_file.write(msg+'\n')


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
        linked_sku_cnt = extract_inventory(file_name)
    except FileNotFoundError as error:
        write_log('{0}: {1}'.format(error.filename, error.strerror), log_filename)
    
    return linked_sku_cnt


if __name__ == '__main__':
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
