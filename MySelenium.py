from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import ElementNotVisibleException
import datetime
import csv


browser = None
log_filename = None


def login(username_str, password_str):
    global browser
    browser = webdriver.Chrome()
    browser.get(('https://app.sellbrite.com/merchants/sign_in'))

    username = browser.find_element_by_id('user_email')
    username.send_keys(username_str)
    password = browser.find_element_by_id('user_password')
    password.send_keys(password_str)
    nextButton = browser.find_element_by_id('clickme')
    nextButton.click()

    bLogin = True
    return bLogin


def get_input_data(filename):
    data = []

    with open(filename) as in_file:
        csv_reader = csv.reader(in_file, delimiter=',')

        line_count = 0;
        for row in csv_reader:
            if 0 == line_count:
                line_count += 1
                continue

            dic = { 'SKU': row[0], 'HAB_1': row[1], 'HAB_2': row[2], 'HAB_3': row[3], 'MC_1': row[4], 'MC_2': row[5], 'MC_3': row[6] }
            data.append(dic)
    
    return data


def generate_linkage(data):
    link_url = '';
    channel_id = ['56358', '56358', '56358', '56020', '56020', '56020']
    columns = ['HAB_1', 'HAB_2', 'HAB_3', 'MC_1', 'MC_2', 'MC_3']

    linked_sku_cnt = 0;

    for i, item in enumerate(data):
        for j, unit in enumerate(columns):
            if '' == item[unit]:
                continue

            link_url = 'https://app.sellbrite.com/channels/{0}?action=filter&channel_id={0}&controller=listings&fb_merchant=true&max_price=&min_price=&query={1}&status=&template_id=&unlinked=true&utf8=%E2%9C%93'.format(channel_id[j], item[unit])
            browser.get((link_url))
            browser.execute_script("""$('a[class="link link-menu-link"]').click();""")

            # wait for transition then continue to fill items
            try:
                search = WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[placeholder="Search Products"]')))
            except TimeoutException as exception:
                write_log("Can't find {0} |{1}, {0}".format(item[unit], item['SKU']), log_filename)
                print("Can't find {0} |{1}, {0}".format(item[unit], item['SKU']))
                continue
            
            query_str = """$('input[placeholder="Search Products"]').attr("value", "SKU");"""
            browser.execute_script(query_str.replace('SKU', item['SKU']))
            search_btn = browser.find_element_by_css_selector('#link_product_modal_form button')
            try:
                search_btn.click()
            except ElementNotVisibleException as exception:
                write_log("Passed SKU {0} with ASIN {1} due to Unvisible Exception |{0}, {1}".format(item['SKU'], item[unit]), log_filename)
                print("Passed SKU {0} with ASIN {1} due to Unvisible Exception |{0}, {1}".format(item['SKU'], item[unit]))

            # wait for transition then continue to fill items
            try:
                select_btn = WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#link-product-search-results #link_product_form button')))
                write_log('{0} linked with {1} |{1}, {0}'.format(item[unit], item['SKU']), log_filename)
                print('{0} linked with {1} |{1}, {0}'.format(item[unit], item['SKU']))
                linked_sku_cnt += 1
            except TimeoutException as exception:
                write_log("Can't find SKU {0} in link with {1} |{0}, {1}".format(item['SKU'], item[unit]), log_filename)
                print("Can't find SKU {0} in link with {1} |{0}, {1}".format(item['SKU'], item[unit]))

    return linked_sku_cnt


def write_log(msg, file_name):
    with open(file_name, mode='a+') as log_file:
        log_file.write(msg+'\n')


if __name__ == '__main__':
    USER_NAME = ''
    PASSWORD = ''

    currentDT = datetime.datetime.now()
    log_filename = currentDT.strftime("%Y%m%d_%H%M%S")
    print("Log file name: {0}".format(log_filename))
    
    input_data = get_input_data('Input.csv')
    login(USER_NAME, PASSWORD)
    
    linked_sku_cnt = generate_linkage(input_data)

    print("generated {0} links with SKU".format(linked_sku_cnt))
    write_log("generated {0} links with SKU".format(linked_sku_cnt), log_filename)
    