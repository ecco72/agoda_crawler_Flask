from flask import Flask, request, render_template, redirect, Response, make_response
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException  #網頁可能在selenium執行cdp之後還有請求，會導致出現這個錯誤
from selenium.webdriver.chrome.service import Service   #新版selenium路徑指定需要
from flask_paginate import Pagination
from bs4 import BeautifulSoup
from datetime import datetime
import json
import time
import csv
import db
import os, sys   #指定路徑用
import webbrowser   #開啟127.0.0.1:5000頁面
from urllib import parse  #response下載的utf-8檔名需要透過quote轉換
import matplotlib.pyplot as plt
from matplotlib.font_manager import fontManager
import io
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

webbrowser.open('http://127.0.0.1:5000', new=2)   #打開搜尋頁面

app = Flask(__name__)
@app.route('/')
def my_form():
    return render_template('form.html')   #首頁 form.html為搜尋頁面表單

@app.route('/', methods=['POST'])   #使用post方式送出form
def my_form_post():
    global checkin, checkout, adults, rooms   #將這四個變數設為全域變數，才可在搜尋結果頁面顯示
    
    city = request.form['city']
    checkin = request.form['checkin']
    checkout = request.form['checkout']
    adults = request.form['adult']
    rooms = request.form['room']
    
    sql = "DELETE FROM agoda"   #清除資料庫表格(因為訂房有時效性)
    db.cursor.execute(sql)
    db.conn.commit()

    mcheckin = datetime.strptime(checkin, '%Y-%m-%d')   #為了算出los(住幾天) 日期轉換
    mcheckout = datetime.strptime(checkout, '%Y-%m-%d')
    los = mcheckout-mcheckin
    los = los.days

    url= "https://www.agoda.com/zh-tw/search?city={}&locale=zh-tw&checkIn={}&checkOut={}&rooms={}&adults={}&children=0&priceCur=TWD".format(city,checkin,checkout,rooms,adults)
    urlfront = 'https://www.agoda.com/zh-tw'
    urlback= "?finalPriceView=1&isShowMobileAppPrice=false&cid=-1&numberOfBedrooms=&familyMode=false&adults={}&children=0&rooms={}&maxRooms=0&isCalendarCallout=false&childAges=&numberOfGuest=0&missingChildAges=false&travellerType=3&showReviewSubmissionEntry=false&currencyCode=TWD&isFreeOccSearch=false&isCityHaveAsq=false&los={}&checkin={}".format(adults,rooms,los,checkin)
    
    options = Options()
    caps = {                          #開啟日誌監聽
            "browserName": "chrome",
            'goog:loggingPrefs': {'performance': 'ALL'}
            }

    for key, value in caps.items():  # 將caps加入到options中
        options.set_capability(key, value)
    
    if getattr(sys, 'frozen', False):   #用 pyinstaller 打包生成的 exe 文件，在運行時動態生成依賴文件，sys._MEIPASS 就是這些依賴文件所在文件夾的路徑
        chromedriver_path = os.path.join(sys._MEIPASS, "chromedriver.exe")
        service = Service(executable_path=chromedriver_path)
        browser = webdriver.Chrome(service=service, options=options)
    else:
        browser = webdriver.Chrome(options=options)

    browser.get(url)
    browser.implicitly_wait(5)
    time.sleep(3)

    while True:    #滾動頁面 並且切換到下一頁
        for i in range(22):
            browser.execute_script('window.scrollBy(0,1500)')
            time.sleep(0.4)
        soup = BeautifulSoup(browser.page_source,'html.parser')
        topbutton = soup.find(id = 'paginationContainer')
        if topbutton.find(id = 'paginationNext') != None:   #下一頁按鈕
            browser.execute_script("document.getElementById('paginationNext').click()")
            time.sleep(3)
        else:
            break

    def filter_type(_type: str):   #設定要過濾的type
        types = [
            'application/javascript', 'application/x-javascript', 'text/css', 'webp', 'image/png', 'image/gif',
            'image/jpeg', 'image/x-icon', 'application/octet-stream', 'image/svg+xml', 'image/webp', 'text/html',
            'font/x-woff2','text/plain'
            ]
        if _type not in types:
            return True
        return False

    performance_log = browser.get_log('performance') #獲取名稱為 performance 的日誌
    for packet in performance_log:
        message = json.loads(packet.get('message')).get('message') #獲取message的數據
        if message.get('method') != 'Network.responseReceived': #如果method 不是 responseReceived 就不往下執行
            continue
        packet_type = message.get('params').get('response').get('mimeType') #獲取response的type
        if not filter_type(_type=packet_type): # 過濾type
            continue
        requestId = message.get('params').get('requestId')
        url = message.get('params').get('response').get('url') #獲取response的url
        if url != 'https://www.agoda.com/graphql/search':
            continue
        
        try:
            resp = browser.execute_cdp_cmd('Network.getResponseBody', {'requestId': requestId}) #使用 cdp
            respstr = str(resp).replace("{'base64Encoded': False, 'body': '{", '{').replace("}}}'}", '}}}').replace('\\', '')  #整理從網站擷取的json檔案
            
            if '{"data":{"citySearch":{"featuredPulseProperties":' in respstr:
                agoda = json.loads(respstr)
                special = agoda['data']['citySearch']['featuredPulseProperties']
                for s in special:
                    name = s['content']['informationSummary']['displayName'].replace("'","''")
                    area = s['content']['informationSummary']['address']['area']['name']
                    rating = s['content']['informationSummary']['rating']
                    link = urlfront + s['content']['informationSummary']['propertyLinks']['propertyPage'] + urlback
                    price = s['pricing']['offers'][0]['roomOffers'][0]['room']['pricing'][0]['price']['perRoomPerNight']['exclusive']['display']
                    img = 'https://'+s['content']['images']['hotelImages'][0]['urls'][0]['value']
                        
                    with open('agoda_search_result.csv', 'a', encoding='UTF-8-sig',newline='') as f:
                        writer = csv.writer(f)
                        
                        fObj = open("agoda_search_result.csv", "r",encoding='UTF-8-sig')   #檢查csv檔案內是否有重複 若有則略過
                        allLines = fObj.readlines()
                        fObj.close()
                        
                        if not '飯店名稱:,'+name+'\n' in allLines:
                            writer.writerow(['飯店名稱:',name])
                            writer.writerow(['位置:',area])
                            writer.writerow(['星級:',rating])
                            writer.writerow(['連結:',link])
                            writer.writerow(['價格:',price])
                            writer.writerow(['圖片:',img])
                            writer.writerow([' '])
                            
                            sql = "select * from agoda where title='{}' and platform='agoda'  ".format(name)
                            db.cursor.execute(sql)
                            
                            sql = "insert into agoda(title,price,loc,link_url,photo_url,rate,platform) values('{}','{}','{}','{}','{}','{}','agoda')".format(name,price,area,link,img,rating)
                            db.cursor.execute(sql)
                            db.conn.commit()
                               
                normal = agoda['data']['citySearch']['properties']
                for n in normal:
                    name = n['content']['informationSummary']['displayName'].replace("'","''")  #單個引號為跳脫字元 改為雙引號
                    area = n['content']['informationSummary']['address']['area']['name']
                    rating = n['content']['informationSummary']['rating']
                    img = 'https://'+ n['content']['images']['hotelImages'][0]['urls'][0]['value']
                    if n['content']['informationSummary'].get('propertyLinks') != None:
                        link = urlfront + n['content']['informationSummary']['propertyLinks']['propertyPage'] + urlback
                    else:
                        link='沒有連結！'
                    if n['pricing']['isAvailable'] == False:
                        price = '這天已經沒有空房了！'
                    else:
                        price = n['pricing']['offers'][0]['roomOffers'][0]['room']['pricing'][0]['price']['perRoomPerNight']['exclusive']['display']
                        
                    with open('agoda_search_result.csv', 'a', encoding='UTF-8-sig',newline='') as f:
                        writer = csv.writer(f)
                        
                        fObj = open("agoda_search_result.csv", "r",encoding='UTF-8-sig')
                        allLines = fObj.readlines()
                        fObj.close()
                        
                        if not '飯店名稱:,'+name+'\n' in allLines:
                            writer.writerow(['飯店名稱:',name])
                            writer.writerow(['位置:',area])
                            writer.writerow(['星級:',rating])
                            writer.writerow(['連結:',link])
                            writer.writerow(['價格:',price])
                            writer.writerow(['圖片:',img])
                            writer.writerow([' '])
                            
                            sql = "select * from agoda where title='{}' and platform='agoda'  ".format(name)
                            db.cursor.execute(sql)
                            
                            sql = "insert into agoda(title,price,loc,link_url,photo_url,rate,platform) values('{}','{}','{}','{}','{}','{}','agoda')".format(name,price,area,link,img,rating)
                            db.cursor.execute(sql)
                            db.conn.commit()
        except WebDriverException:    #網頁可能在程式執行cdp之後還有請求，會導致出現這個錯誤，因為要抓的<search> json 在執行cdp前就已讀取完畢，可以忽略這個錯誤
            pass
        
    os.remove('agoda_search_result.csv')   #將比對用的csv刪除
    sql = "DELETE FROM agoda WHERE price = '這天已經沒有空房了！' or link_url = '沒有連結！'"   #整理資料庫內資料
    db.cursor.execute(sql)
    db.conn.commit()
    browser.close()    
    return redirect("search", code=302) #302代表我們輸入的連結還在使用，然後再重新導向一個新的連結(預設為302)

@app.route('/search')
def my_form2():
    return render_template('search_form.html')

@app.route('/hotels')
def goods():
    p = request.args.get('p',' ')    #預設空白
    startp = int(request.args.get('startp'))
    endp = int(request.args.get('endp'))
    area = request.args.get('area',' ')
    page = int(request.args.get('page',1))   #http://127.0.0.1:5000/news?page=2
    
    if page == 1:
        if p == ' ' and area == ' ':
            sql = "select title,price,link_url,photo_url,loc,rate from agoda where price between {} and {} order by price asc limit 36".format(startp,endp)
            sql2 = "select count(*) from agoda where price between {} and {} order by price".format(startp,endp)
        elif area == ' ':
            sql = "select title,price,link_url,photo_url,loc,rate from agoda where price between {} and {} and title like '%{}%' order by price asc limit 36".format(startp,endp,p)
            sql2 = "select count(*) from agoda where price between {} and {} and title like '%{}%' order by price".format(startp,endp,p)
        elif p == ' ':
            sql = "select title,price,link_url,photo_url,loc,rate from agoda where price between {} and {} and loc like '%{}%' order by price asc limit 36".format(startp,endp,area)
            sql2 = "select count(*) from agoda where price between {} and {} and loc like '%{}%' order by price".format(startp,endp,area)
        else:
            sql = "select title,price,link_url,photo_url,loc,rate from agoda where price between {} and {} and title like '%{}%' and loc like '%{}%' order by price asc limit 36".format(startp,endp,p,area)
            sql2 = "select count(*) from agoda where price between {} and {} and title like '%{}%' and loc like '%{}%' order by price".format(startp,endp,p,area)
    else:
        starpage = page - 1
        if p == ' ' and area == ' ':
            sql = "select title,price,link_url,photo_url,loc,rate from agoda where price between {} and {} order by price asc limit {},{}".format(startp, endp, starpage*36, 36)
            sql2 = "select count(*) from agoda where price between {} and {} order by price".format(startp, endp)
        elif area == ' ':
            sql = "select title,price,link_url,photo_url,loc,rate from agoda where price between {} and {} and title like '%{}%' order by price asc limit {},{}".format(startp, endp, p, starpage*36, 36)
            sql2 = "select count(*) from agoda where price between {} and {} and title like '%{}%' order by price".format(startp, endp, p)
        elif p == ' ':
            sql = "select title,price,link_url,photo_url,loc,rate from agoda where price between {} and {} and loc like '%{}%' order by price asc limit {},{}".format(startp, endp, area, starpage*36, 36)
            sql2 = "select count(*) from agoda where price between {} and {} and loc like '%{}%' order by price".format(startp, endp, area)
        else:
            sql = "select title,price,link_url,photo_url,loc,rate from agoda where price between {} and {} and title like '%{}%' and loc like '%{}%' order by price asc limit {},{}".format(startp,endp,p,area, starpage*36, 36)
            sql2 = "select count(*) from agoda where price between {} and {} and title like '%{}%' and loc like '%{}%' order by price".format(startp,endp,p,area)
        
    db.cursor.execute(sql)
    result = db.cursor.fetchall()
    
    db.cursor.execute(sql2)   #為了抓總數量才可以正確顯示頁數
    datacount = db.cursor.fetchone()
    count = int(datacount[0])
    
    pagination = Pagination(page = page, total = count, per_page = 36, css_framework='foundation')  #將頁數變數、總筆數、一頁幾個輸入
    
    return render_template('hotels.html', **globals(), **locals())

@app.route("/getCSV")
def getCSV():
    sql = "select title,price,link_url,photo_url,loc,rate from agoda order by price asc"
    db.cursor.execute(sql)
    result = db.cursor.fetchall()
    title = '飯店名稱,每間每晚價格,訂房連結,區域,星級\n'
    content = ''
    
    for row in result:
        content = content + row[0].replace(',','')+','+str(row[1])+','+row[2]+','+row[4]+','+str(row[5])+'\n'  #有些飯店名稱有逗號 要取代掉
        
    csv = title + content
    prefilename = datetime.now().strftime("%Y%m%d%H%M")+'訂房查詢資料'
    filename = parse.quote(prefilename)
    Response.charset= 'utf-8-sig'
    response = make_response(csv)
    cd = f'attachment; filename={filename}.csv'
    response.headers['Content-Disposition'] = cd 
    response.mimetype='text/csv'

    return response

@app.route("/statistic.png")
def statistic():
    fontManager.addfont('TaipeiSansTCBeta-Regular.ttf')
    plt.rc('font', family='Taipei Sans TC Beta')
    plt.rcParams['axes.unicode_minus'] = False
    
    def img(sqlcmd):
        areasql = f"select loc,{sqlcmd} from agoda GROUP BY loc ORDER BY COUNT(loc)"
        db.cursor.execute(areasql)
        arearesult = db.cursor.fetchall()
        
        hotelprice = []
        hotelarea = []
        
        for a in arearesult:
            hotelarea.append(a[0])
            hotelprice.append(a[1])
    
        if sqlcmd == 'COUNT(loc)':
            ax1 = fig.add_subplot(411)
            ax1.bar(hotelarea,hotelprice,zorder=2)
            ax1.grid(zorder=0)
            ax1.set_title('各區域飯店空房數', fontsize='20')
            
        elif sqlcmd == 'avg(price)':
            ax2 = fig.add_subplot(412)
            ax2.bar(hotelarea,hotelprice,zorder=2)
            ax2.grid(zorder=0)
            ax2.set_title('各區域飯店平均價', fontsize='20')
            
        elif sqlcmd == 'max(price)':
            ax3 = fig.add_subplot(413)
            ax3.bar(hotelarea,hotelprice,zorder=2)
            ax3.grid(zorder=0)
            ax3.set_title('各區域飯店最高價', fontsize='20')
            
        else:
            ax4 = fig.add_subplot(414)
            ax4.bar(hotelarea,hotelprice,zorder=2)
            ax4.grid(zorder=0)
            ax4.set_title('各區域飯店最低價', fontsize='20')

    fig = plt.figure(figsize=(20,32))
    img('COUNT(loc)')
    img('avg(price)')
    img('max(price)')
    img('min(price)')
    fig.tight_layout(pad=5)  #子圖間距

    output = io.BytesIO()
    FigureCanvas(fig).print_png(output)
    fig.savefig("test.png")
    return Response(output.getvalue(), mimetype='image/png')

@app.route('/plot')
def plot():
    
    return render_template('plot.html')

app.run()