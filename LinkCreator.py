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

def generate_linkage(filename):
    link_url = '';
    linked_sku_cnt = 0;

    data = None
    header = [{}]
    with open(filename) as in_file:
        with open(result_filename, mode='w') as out_file:
            reader = csv.reader(in_file, delimiter=',')
            for i, item in enumerate(reader):
                if 0 == i:
                    # Extract header information
                    for j in range(1, len(item)):
                        tokens = item[j].strip().split(" ")
                        header.append({ 'market': tokens[0].strip().lower(), 'seller': tokens[1].strip().lower() })    

                    # Write header to output file
                    out_file.write(item[0])
                    for j in range(1, len(item)):
                        out_file.write(",{}".format(item[j]))
                    out_file.write('\n')
                    continue
        
                # Item section
                cnt = len(item)-1 # Number of seller of the item

                # Retrieve SKU's product id
                item[0] = item[0].strip()
                try:
                    response = session.get(meta['sku_url'].format(item[0]))
                    res = response.json()
                    if len(res) < 1 or 1 < len(res):
                        if len(res) < 1:
                            write_log("{0}. Can't find sku'id: {1}".format(i, item[0]), log_filename)
                        else:
                            write_log("{0}. Not unique sku id: {1}".format(i, item[0]), log_filename)

                        out_file.write(item[0])
                        for j in range(1, len(item)):
                            out_file.write(',{0}'.format(item[j]))
                        out_file.write('\n')
                        continue
                    
                    sku_id = res[0]['product_id'];
                    write_log('{0}. SKU id: {1} ({2})'.format(i, item[0], sku_id), log_filename)
                except json.decoder.JSONDecodeError as error:
                    write_log("Login fail! please check the ID and Password.", log_filename)
                    return linked_sku_cnt

                for j in range(1, len(item)):
                    # Skip empty or invalid code
                    item[j] = item[j].strip()
                    if '' == item[j] or 'NoListing' == item[j]:
                        cnt -= 1
                        item[j] = ''
                        continue

                    market = header[j]['market'] # Market of the seller
                    seller = header[j]['seller'] # Select seller

                    # Retrieve product id from listing
                    try:
                        listing_url = meta[market]['url'].format(meta[market][seller], item[j])
                        response = session.get(listing_url)
                        soup = BeautifulSoup(response.text, 'html.parser')
                        res = soup.find('table', class_='slickgrid-table').find('tbody').find_all('tr')
                        if len(res) < 1:
                            write_log("{0}-{1}. Can't find listing item'id: {2}".format(i, j, item[j]), log_filename)
                            continue
                        if 1 < len(res):
                            write_log("{0}-{1}. Not unique listing item id: {2}".format(i, j, item[j]), log_filename)
                            continue
                        data_key = json.loads(res[0]['data-key'])
                        origin_id = data_key['id']
                        write_log("{0}-{1}. Origin: {2} ({3})".format(i, j, item[j], origin_id), log_filename)
                    except KeyError as error:
                        write_log("Error! {0}-{1}. Invalid header : {2}".format(i, j, error.args[0]), log_filename)
                        return 0

                    # Generate link
                    query_str = """return (function() {
                                            let ret = '';
                                            $.ajax({type: 'POST',
                                                url: "https://app.sellbrite.com/api/listings/link_product",
                                                data: { 'id': 'origin_id', 'product_id': 'sku_id' },
                                                success: function(result) {
                                                    ret = result.linked;
                                                },
                                                async: false
                                            });
                                            return ret;
                                        })();"""
                    try:
                        link_ret = session.driver.execute_script(query_str.replace('origin_id', str(origin_id)).replace('sku_id', str(sku_id)))
                        if link_ret == True:
                            write_log('{0}-{1}. Generated link between {2} and {3}'.format(i, j, item[0], item[j]), log_filename)
                            cnt -= 1
                            item[j] = ''
                            linked_sku_cnt += 1
                    except TimeoutException as exception:
                        write_log('{0}-{1}. Timeout with linking {2} and {3}'.format(i, j, item[0], item[j]), log_filename)

                if 0 < cnt:
                    out_file.write(item[0])
                    for j in range(1, len(item)):
                        out_file.write(',{0}'.format(item[j]))
                    out_file.write('\n')

    return linked_sku_cnt


def write_log(msg, file_name):
    print(msg)
    with open(file_name, mode='a+') as log_file:
        log_file.write(msg+'\n')


def run(file_name):
    global log_filename
    global result_filename

    log_filename = '{0}.{1}.log'.format(file_name.replace('.csv', ''), currentDT.strftime("%Y%m%d_%H%M%S"))
    result_filename = '{0}.{1}.remain.csv'.format(file_name.replace('.csv', ''), currentDT.strftime("%Y%m%d_%H%M%S"))
    print("Log file name: {0}".format(log_filename))
    print("Remain file name: {0}".format(result_filename))

    write_log('Start with input file: {0}'.format(file_name), log_filename)
    
    linked_sku_cnt = 0

    try:
        linked_sku_cnt = generate_linkage(file_name)
    except FileNotFoundError as error:
        write_log('{0}: {1}'.format(error.filename, error.strerror), log_filename)
    
    return linked_sku_cnt


if __name__ == '__main__':
    USER_NAME = ''
    PASSWORD = ''
    input_file_name = ''
    SHOW_BROWSER = False

    TEST = 0

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
