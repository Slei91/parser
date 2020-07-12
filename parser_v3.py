import requests
import os
import csv
import tkinter
import time
import multiprocessing
import logging
from tkinter import messagebox as mb
from bs4 import BeautifulSoup


HEADERS = (
    '_ID_',
    '_CATEGORY_',
    '_NAME_',
    '_MODEL_',
    '_SKU_',
    '_EAN_',
    '_JAN_',
    '_ISBN_',
    '_MPN_',
    '_UPC_',
    '_MANUFACTURER_',
    '_SHIPPING_',
    '_LOCATION_',
    '_PRICE_',
    '_POINTS_',
    '_REWARD_POINTS_',
    '_QUANTITY_',
    '_STOCK_STATUS_ID_',
    '_STOCK_STATUS_',
    '_LENGTH_',
    '_WIDTH_',
    '_HEIGHT_',
    '_WEIGHT_',
    '_META_TITLE_',
    '_META_KEYWORDS_',
    '_META_DESCRIPTION_',
    '_DESCRIPTION_',
    '_PRODUCT_TAG_',
    '_IMAGE_',
    '_SORT_ORDER_',
    '_STATUS_',
    '_SEO_KEYWORD_',
    '_DISCOUNT_',
    '_SPECIAL_',
    '_OPTIONS_',
    '_FILTERS_',
    '_ATTRIBUTES_',
    '_IMAGES_',
    '_PRODUCT_IMAGES_',
    '_RELATED_NAME_',
    '_STORE_ID_',
    '_URL_'
)


class Client:
    result = []

    def __init__(self, page_url):
        self.page_url = page_url
        self.session = requests.Session()
        self.session.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/83.0.4103.61 Safari/537.36 ',
            'Accept_Language': 'ru-RU',
        }
        self.host_img_dir_path = 'consolari.beget.tech/public_html/image/catalog/rucki-pic'
        self.dir_name = None

    def load_catalog_page(self):
        catalog_page = self.session.get(self.page_url)
        catalog_page.raise_for_status()
        return catalog_page

    def load_page(self, url, params=None):
        r = requests.get(url, headers=self.session.headers, params=params)
        return r

    @staticmethod
    def get_last_page_num(soup):
        try:
            last_page = soup.find('li', class_='last-page').find_next('a').get('href')
            last_page = int(''.join([symbol for symbol in last_page if symbol.isdigit()]))
        except AttributeError:
            return 1
        return last_page

    def save_csv(self):
        with open(f'{self.dir_name}.csv', 'w', encoding='utf8', newline='') as file:
        # with open(f'{self.dir_name}.csv', 'w', encoding='cp1251', newline='') as file:
            writer = csv.writer(file, delimiter=';')
            writer.writerow(HEADERS)
            for item in self.result:
                try:
                    writer.writerow(item)
                except:
                    continue

    def parse_url(self):
        page = self.load_catalog_page()
        soup = BeautifulSoup(page.text, 'lxml')
        last_page = self.get_last_page_num(soup)

        # Получаю поле производителя
        try:
            good_manufacturer = soup.select_one('ul.breadcrumbs > :nth-child(4)').get_text()
        except:
            good_manufacturer = None

        # Создаю имя папки для картинок
        self.dir_name = soup.select_one('ul.breadcrumbs > :last-child').get_text()      # отвечает за название файла

        goods_links_gen = None
        for page_num in range(1, last_page + 1):
            goods_page_link = self.load_page(url=self.page_url, params={'page': page_num})
            soup = BeautifulSoup(goods_page_link.text, 'lxml')
            goods_page_links = soup.find_all('a', class_='product-image')
            goods_links_gen = (link['href'] for link in goods_page_links)

        collector = multiprocessing.Queue(maxsize=-1)
        result_data_list = [ParseUrl(url=good_page, good_manufacturer=good_manufacturer, collector=collector)
                            for good_page in goods_links_gen]

        for item in result_data_list:
            item.start()

        ''' Пока есть живые потоки, пока есть данные в очереди программа собирает данные,
            если процессы закончились и в очереди нет данных, то происходит выход из цикла.
            Если собирать данные после join процессов, то получается deadlock,
            из-за того, что в очередь получает lock из-за нехватки места, а join процессов ждет очередь
        '''
        while True:
            running = any(p.is_alive() for p in result_data_list)
            while not collector.empty():
                self.result.append(collector.get().values())
            if not running:
                break

        for item in result_data_list:
            item.join()


class ParseUrl(Client, multiprocessing.Process):
    def __init__(self, good_manufacturer, url, collector, *args, **kwargs):
        Client.__init__(self, page_url=url)
        multiprocessing.Process.__init__(self, *args, **kwargs)
        self.url = url
        self.good_manufacturer = good_manufacturer
        self.collector = collector

    def run(self):
        logging.info(f'Процесс {self.name} начал выполняться')
        good_page = self.load_page(self.url)
        soup = BeautifulSoup(good_page.text, 'lxml')

        # Название модели
        try:
            model_name = soup.select('div.product-name > h1')[0].get_text()
        except:
            model_name = None

        # Сопутствующие товары
        related_products_list = []
        related_products = soup.select('form > div.item-info > div.product-name > a')
        for item_name in related_products:
            related_products_list.append(item_name.get_text())

        # Словарь характеристик

        attributes = {}

        characteristics_table = soup.select('table.table-box > tbody > tr')
        for tr in characteristics_table:
            key = tr.find('span', class_='value').get_text()
            attributes[key] = tr.find('td', class_='data').get_text()

        options = soup.select('select.selectBox > option')
        for option in options:
            # Название цвета
            good_color = option.get_text()
            try:
                # id по value
                good_value_id = option.get('value')
                # Артикул(модель)
                good_art = soup.find('div', {'class': 'goodsDataMainModificationsList', 'rel': good_value_id}) \
                    .find_next('input', {'name': 'art_number'}).get('value')
                # Цена
                good_price = soup.find('div', {'class': 'goodsDataMainModificationsList', 'rel': good_value_id}) \
                    .find_next('input', {'name': 'price_now'}).get('value')

                self.collector.put(dict(
                    id=None,
                    category=None,
                    name=f'{model_name} {good_color}',
                    model=good_art,
                    sku=None,
                    ean=None,
                    jan=None,
                    isbn=None,
                    mpn=None,
                    upc=None,
                    manufacturer=self.good_manufacturer,
                    SHIPPING=1,
                    LOCATION=None,
                    PRICE=good_price,
                    POINTS=0,
                    REWARD_POINTS=None,
                    QUANTITY=100,
                    STOCK_STATUS_ID=1,
                    STOCK_STATUS='В наличии',
                    LENGTH=0,
                    WIDTH=0,
                    HEIGHT=0,
                    WEIGHT=0,
                    META_TITLE=f'{model_name} {good_color}, купить в Москве',
                    META_KEYWORDS=f'{model_name if model_name else ""} {good_art if good_art else ""} '
                                  f'{self.good_manufacturer if self.good_manufacturer else ""}',
                    META_DESCRIPTION=None,
                    DESCRIPTION=f'{model_name} от итальянского производителя '
                                f'{self.good_manufacturer if self.good_manufacturer else ""}.',
                    PRODUCT_TAG=f'{model_name}, {self.good_manufacturer if self.good_manufacturer else ""}',
                    IMAGE=None,
                    SORT_ORDER=0,
                    STATUS=1,
                    SEO_KEYWORD=None,
                    DISCOUNT=None,
                    SPECIAL=None,
                    OPTIONS=None,
                    FILTERS=f'Стиль|{attributes["Стиль"] if "Стиль" in attributes else ""}\n'
                            f'Цвет|{good_color}\nБренд|{self.good_manufacturer if self.good_manufacturer else ""}',
                    ATTRIBUTES='\n'.join([f'Характеристики|{key}|{value}' for key, value in attributes.items()]),
                    IMAGES=None,
                    PRODUCT_IMAGES=None,
                    RELATED_NAME=','.join(related_products_list),
                    STORE_ID=0,
                    URL=None
                ))

            except:
                continue
        logging.info(f'Процесс {self.name} закончил выполняться')


def main():
    logging.basicConfig(level=logging.INFO)

    def click_button():
        url = user_input.get()
        start_parse = time.time()
        parsing = Client(page_url=url)
        parsing.parse_url()
        parsing.save_csv()
        print(f'Парсер отработал за {time.time() - start_parse} секунд')
        mb.showinfo('Готово', f'Парсер завершил работу, путь к файлам: {os.getcwd()}')

    window = tkinter.Tk()
    window.title('Парсер')
    lbl = tkinter.Label(window, text='Введите ссылку')
    lbl.grid(column=0, row=0)
    user_input = tkinter.Entry(window, width=100)
    user_input.grid(column=0, row=1, padx=10)
    btn = tkinter.Button(window, text="Парсить!", command=click_button)
    btn.grid(column=0, row=2, pady=10)

    window.mainloop()


if __name__ == '__main__':
    main()
