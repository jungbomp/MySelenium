from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import ElementNotVisibleException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.common.exceptions import WebDriverException
import sys
import os
import datetime
import csv


browser = None
log_filename = None
result_filename = None


def login(username_str, password_str):
    global browser
    options = webdriver.ChromeOptions()
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--ignore-ssl-errors')
    browser = webdriver.Chrome(chrome_options=options)
    browser.get(('https://app.sellbrite.com/merchants/sign_in'))

    username = browser.find_element_by_id('user_email')
    username.send_keys(username_str)
    password = browser.find_element_by_id('user_password')
    password.send_keys(password_str)
    nextButton = browser.find_element_by_id('clickme')
    nextButton.click()

    bLogin = True
    return bLogin


def get_input_data(filename, header):
    data = []

    with open(filename) as in_file:
        csv_reader = csv.reader(in_file, delimiter=',')

        line_count = 0;
        for row in csv_reader:
            if 0 == line_count:
                line_count += 1
                continue

            dic = {}
            for i, col in enumerate(header):
                try:
                    dic[header[i]] = row[i].strip()
                except IndexError as error:
                    dic[header[i]] = ''
            data.append(dic)
    
    return data


def generate_linkage(data, labels, columns, channel_id, url):
    link_url = '';
    linked_sku_cnt = 0;

    with open(result_filename, mode='w') as out_file:
        for i, label in enumerate(labels):
            if 0 < i:
                out_file.write(",{}".format(label))
            else:
                out_file.write(label)
        out_file.write('\n')

        for i, item in enumerate(data):
            cnt = len(columns)

            for j, unit in enumerate(columns):
                if '' == item[unit] or 'NoListing' == item[unit]:
                    cnt -= 1
                    item[unit] = ''
                    continue

                link_url = url.format(channel_id[j], item[unit])
                browser.get((link_url))

                try:
                    ret = browser.find_element_by_css_selector('div[class="linked-icon link-size-small"]')
                    sku = browser.find_element_by_css_selector('div[class="slick-cell l5 r5"]').text

                    if item['SKU'] == sku:
                        cnt -= 1
                        item[unit] = ''
                        continue
                    
                    browser.execute_script("""$('a[class="link unlink-menu-link"]').click();""")
                    unlink_url = link_url.replace("linked=true", "unlinked=true")
                    browser.get((unlink_url))
                    ret = browser.find_element_by_css_selector('div[class="unlinked-icon link-size-small"]')
                except NoSuchElementException as exception:
                    write_log("Can't find {0} |{1},{0}".format(item[unit], item['SKU']), log_filename)
                    continue
                
                browser.execute_script("""$('a[class="link link-menu-link"]').click();""")

                # wait for transition then continue to fill items
                try:
                    search = WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[placeholder="Search Products"]')))
                except TimeoutException as exception:
                    write_log("Can't find {0} |{1},{0}".format(item[unit], item['SKU']), log_filename)
                    continue
                
                query_str = """$('input[placeholder="Search Products"]').attr("value", "SKU");"""
                browser.execute_script(query_str.replace('SKU', item['SKU']))
                search_btn = browser.find_element_by_css_selector('#link_product_modal_form button')
                try:
                    search_btn.click()
                except ElementNotVisibleException as exception:
                    write_log("Passed SKU {0} with ASIN {1} due to Unvisible Exception |{0},{1}".format(item['SKU'], item[unit]), log_filename)
                except WebDriverException as exception:
                    write_log("Passed SKU {0} with ASIN {1} due to Other element would receive the click |{0},{1}".format(item['SKU'], item[unit]), log_filename)

                # wait for transition then continue to fill items
                try:
                    select_btn = WebDriverWait(browser, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#link-product-search-results #link_product_form button')))
                    select_btn.click()
                    write_log('{0} linked with {1} |{1},{0}'.format(item[unit], item['SKU']), log_filename)
                    item[unit] = ''
                    linked_sku_cnt += 1
                    cnt -= 1
                except TimeoutException as exception:
                    write_log("Can't find SKU {0} in link with {1} |{0},{1}".format(item['SKU'], item[unit]), log_filename)
                except ElementNotVisibleException as exception:
                    write_log("Passed SKU {0} with ASIN {1} due to Unvisible Exception |{0},{1}".format(item['SKU'], item[unit]), log_filename)
                except StaleElementReferenceException as exception:
                    write_log("Passed SKU {0} with ASIN {1} due to StaleElementReference Exception |{0},{1}".format(item['SKU'], item[unit]), log_filename)
                except WebDriverException as exception:
                    write_log("Passed SKU {0} with ASIN {1} due to not clickable Exception |{0},{1}".format(item['SKU'], item[unit]), log_filename)

            if 0 < cnt:
                out_file.write(item['SKU'])
                for unit in columns:
                    out_file.write(',{0}'.format(item[unit]))
                out_file.write('\n')

    return linked_sku_cnt


def write_log(msg, file_name):
    print(msg)
    with open(file_name, mode='a+') as log_file:
        log_file.write(msg+'\n')


def run(file_name):
    global log_filename
    global result_filename

    # Meta data for Amazon
    # header = ['SKU', 'HAB_1', 'HAB_2', 'HAB_3', 'MC_1', 'MC_2', 'MC_3']
    # channel_id = ['56358', '56358', '56358', '56020', '56020', '56020']
    # columns = ['HAB_1', 'HAB_2', 'HAB_3', 'MC_1', 'MC_2', 'MC_3']
    # labels = ['Shopify Hat and Beyond (Standard)', 'Amazon Hat and Beyond', 'Amazon Hat and Beyond (version 2)', 'Amazon Hat and Beyond (version 3)', 'Amazon Ma Croix', 'Amazon Ma Croix (version 2)', 'Amazon Ma Croix (version 3)']
    # url = 'https://app.sellbrite.com/channels/{0}?action=filter&channel_id={0}&controller=listings&fb_merchant=true&max_price=&min_price=&query={1}&status=&template_id=&unlinked=true&utf8=%E2%9C%93'

    # Meta data for Walmart
    header = ['SKU', 'HAB_1', 'HAB_2', 'HAB_3', 'HAB_4', 'HAB_5']
    channel_id = ['56021', '56021', '56021', '56021', '56021']
    columns = ['HAB_1', 'HAB_2', 'HAB_3', 'HAB_4', 'HAB_5']
    labels = ['Shopify Hat and Beyond (Standard)', 'Walmart Hat and Beyond', 'Walmart Hat and Beyond (version 2)', 'Walmart Hat and Beyond (version 3)', 'Walmart Hat and Beyond (version 4)', 'Walmart Hat and Beyond (version 5)']
    url = 'https://app.sellbrite.com/channels/{0}?action=filter&channel_id={0}&controller=listings&max_price=&min_price=&query={1}&status=&template_id=&linked=true&utf8=%E2%9C%93'

    log_filename = '{0}.{1}.log'.format(file_name.replace('.csv', ''), currentDT.strftime("%Y%m%d_%H%M%S"))
    result_filename = '{0}.{1}.remain.csv'.format(file_name.replace('.csv', ''), currentDT.strftime("%Y%m%d_%H%M%S"))
    print("Log file name: {0}".format(log_filename))
    print("Remain file name: {0}".format(result_filename))
    
    input_data = get_input_data(file_name, header)
    linked_sku_cnt = generate_linkage(input_data, labels, columns, channel_id, url)

    return linked_sku_cnt



if __name__ == '__main__':
    USER_NAME = ''
    PASSWORD = ''
    input_file_name = ''

    TEST = 

    if TEST != 1:
        if len(sys.argv) < 2:
            print('Usage: python LinkChecker.py <Input_file_name.csv> [USER_ID] [PASSWORD]')
            exit()

        if 2 == len(sys.argv):
            input_file_name = sys.argv[1]

        if 4 == len(sys.argv):
            input_file_name = sys.argv[1]
            USER_NAME = sys.argv[2]
            PASSWORD = sys.argv[3]

    currentDT = datetime.datetime.now()
    login(USER_NAME, PASSWORD)

    if os.path.isdir(input_file_name):
        files = os.listdir(input_file_name)
        for file_name in files:
            input_file = os.path.join(input_file_name, file_name)
            print("Current_file: {0}".format(input_file))
            write_log("generated {0} links with SKU".format(run(input_file)), log_filename)
    else:
        write_log("generated {0} links with SKU".format(run(input_file_name)), log_filename)

    browser.quit()
   
