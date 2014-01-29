#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''get lunar calendar from hk observatory '''

__license__ = 'BSD'
__copyright__ = '2014, Chen Wei <weichen302@gmail.com>'
__version__ = '0.0.2'

from StringIO import StringIO
from datetime import datetime
from datetime import timedelta
import cookielib
import getopt
import gzip
import os
import re
import sqlite3
import sys
import urllib2
import zlib

APPDIR = os.path.abspath(os.path.dirname(__file__))
DB_FILE = os.path.join(APPDIR, 'db', 'lunarcal.sqlite')
RE_CAL = re.compile(u'(\d{4})年(\d{1,2})月(\d{1,2})日')
PROXY = {'http': 'http://localhost:8001'}
URL = 'http://gb.weather.gov.hk/gts/time/calendar/text/T%dc.txt'
OUTPUT = os.path.join(APPDIR, 'chinese_lunar_%s_%s.ics')

ICAL_HEAD = ('BEGIN:VCALENDAR\n'
             'PRODID:-//Chen Wei//Chinese Lunar Calendar//EN\n'
             'VERSION:2.0\n'
             'CALSCALE:GREGORIAN\n'
             'METHOD:PUBLISH\n'
             'X-WR-CALNAME:农历\n'
             'X-WR-TIMEZONE:Asia/Shanghai\n'
             'X-WR-CALDESC:中国农历1901-2100, 包括节气. 数据来自香港天文台')

ICAL_SEC = ('BEGIN:VEVENT\n'
            'DTSTART;VALUE=DATE:%s\n'
            'DTEND;VALUE=DATE:%s\n'
            'SUMMARY:%s\n'
            'END:VEVENT')

ICAL_END = 'END:VCALENDAR'

CN_DAY = {u'初二': 2, u'初三': 3, u'初四': 4, u'初五': 5, u'初六': 6,
          u'初七': 7, u'初八': 8, u'初九': 9, u'初十': 10, u'十一': 11,
          u'十二': 12, u'十三': 13, u'十四': 14, u'十五': 15, u'十六': 16,
          u'十七': 17, u'十八': 18, u'十九': 19, u'二十': 20, u'廿一': 21,
          u'廿二': 22, u'廿三': 23, u'廿四': 24, u'廿五': 25, u'廿六': 26,
          u'廿七': 27, u'廿八': 28, u'廿九': 29, u'三十': 30}

CN_MON = {u'正月': 1, u'二月': 2, u'三月': 3, u'四月': 4,
          u'五月': 5, u'六月': 6, u'七月': 7, u'八月': 8,
          u'九月': 9, u'十月': 10, u'十一月': 11, u'十二月': 12,

          u'閏正月': 101, u'閏二月': 102, u'閏三月': 103, u'閏四月': 104,
          u'閏五月': 105, u'閏六月': 106, u'閏七月': 107, u'閏八月': 108,
          u'閏九月': 109, u'閏十月': 110, u'閏十一月': 111, u'閏十二月': 112}


def initdb():
    try:
        print 'creating db dir'
        os.mkdir(os.path.join(APPDIR, 'db'))
    except OSError:
        pass

    conn = sqlite3.connect(DB_FILE)
    db = conn.cursor()
    db.execute('''CREATE TABLE IF NOT EXISTS ical (
                    id INTEGER PRIMARY KEY,
                    date TEXT UNIQUE,
                    lunardate TEXT,
                    holiday TEXT,
                    jieqi TEXT)''')
    conn.commit()
    db.close()


def query_db(query, args=(), one=False):
    ''' wrap the db query, fetch into one step '''
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    db = conn.cursor()
    cur = db.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


class HTTPCompress(urllib2.BaseHandler):
    """A handler to add gzip capabilities to urllib2 requests """
    def http_request(self, req):
        req.add_header("Accept-Encoding", "gzip, deflate")
        req.add_header("User-Agent",
       "Mozilla/5.0 (X11; U; Linux i686; en-US; rv:1.9.2.13) Gecko/20101203")
        return req

    def http_response(self, req, resp):
        old_resp = resp
        if resp.headers.get("content-encoding") == "gzip":
            data = gzip.GzipFile(fileobj=StringIO(resp.read()), mode="r")
            resp = urllib2.addinfourl(data, old_resp.headers,
                                      old_resp.url, old_resp.code)
            resp.msg = old_resp.msg
        if resp.headers.get("content-encoding") == "deflate":
            data = zlib.decompress(resp.read(), -zlib.MAX_WBITS)
            resp = urllib2.addinfourl(data, old_resp.headers,
                                      old_resp.url, old_resp.code)
            resp.msg = old_resp.msg
        return resp


def browser(proxy=None):
    gzip_support = HTTPCompress
    cj = cookielib.CookieJar()
    cookie_support = urllib2.HTTPCookieProcessor(cj)
    proxy_support = urllib2.ProxyHandler(proxy)
    if proxy:
        opener = urllib2.build_opener(gzip_support, urllib2.HTTPHandler,
                                     cookie_support, proxy_support)
    else:
        opener = urllib2.build_opener(gzip_support, urllib2.HTTPHandler,
                                                     cookie_support)
    return opener


def parse_hko(pageurl):
    ''' parse lunar calender from hk Obs
    Args: pageurl
    Return:
          a string contains all posts'''

    print 'grabbing and parsing %s' % pageurl
    br = browser(PROXY)
    lines = br.open(pageurl).readlines()
    sql_nojq = ('insert or replace into ical (date,lunardate) '
                'values(?,?) ')
    sql_jq = ('insert or replace into ical (date,lunardate,jieqi) '
              'values(?,?,?) ')
    conn = sqlite3.connect(DB_FILE)
    db = conn.cursor()
    for line in lines:
        line = line.decode('big5')
        m = RE_CAL.match(line)
        if m:
            fds = line.split()
            # add leading zero to month and day
            if len(m.group(2)) == 1:
                str_m = '0%s' % m.group(2)
            else:
                str_m = m.group(2)
            if len(m.group(3)) == 1:
                str_d = '0%s' % m.group(3)
            else:
                str_d = m.group(3)

            dt = '%s-%s-%s' % (m.group(1), str_m, str_d)
            if len(fds) > 3:  # last field is jieqi
                db.execute(sql_jq, (dt, fds[1], fds[3]))
            else:
                db.execute(sql_nojq, (dt, fds[1]))
    conn.commit()


def update_cal():
    ''' fetch lunar calendar from HongKong Obs, parse it and save to db'''
    for y in xrange(1901, 2101):
        parse_hko(URL % y)


def gen_cal(start, end, fp):
    ''' generate lunar calender in iCalendar format.
    Args:
        start and end date in ISO format, like 2010-12-31
        fp: path to output file
    Return:
        none
        '''

    sql = ('select date, lunardate, holiday, jieqi from ical '
           'where date>=? and date<=? order by date')
    rows = query_db(sql, (start, end))
    lines = [ICAL_HEAD]
    oneday = timedelta(days=1)
    for r in rows:
        dt = datetime.strptime(r['date'], '%Y-%m-%d')

        ld = [r['lunardate']]
        if r['holiday']:
            ld.append(r['holiday'])
        if r['jieqi']:
            ld.append(r['jieqi'])
        line = ICAL_SEC % (dt.strftime('%Y%m%d'),
                           (dt + oneday).strftime('%Y%m%d'), ' '.join(ld))
        lines.append(line.encode('utf8'))
    lines.append(ICAL_END)
    outputf = open(fp, 'w')
    outputf.write('\n'.join(lines))
    outputf.close()
    print 'iCal lunar calendar from %s to %s saved to %s' % (start, end, fp)


def post_process():
    ''' there are several mistakes in HK OBS data, the following date
    do not have a valid lunar date, instead are the weekday names, they
    are all 三十 '''
    sql_update = 'update ical set lunardate=? where date=?'

    HK_ERROR = ('2036-01-27', '2053-12-09', '2056-03-15',
                '2063-07-25', '2063-10-21', '2063-12-19')
    conn = sqlite3.connect(DB_FILE)
    db = conn.cursor()
    for d in HK_ERROR:
        print 'fix lunar date for %s' % d
        db.execute(sql_update, (u'三十', d))
    conn.commit()


def update_holiday():
    ''' write chinese traditional holiday to db

    腊八节(腊月初八)     除夕(腊月的最后一天)     春节(一月一日)
    元宵节(一月十五日)   寒食节(清明的前一天)     端午节(五月初五)
    七夕节(七月初七)     中元节(七月十五日)       中秋节(八月十五日)
    重阳节(九月九日)     下元节(十月十五日)

    '''
    sql = 'select * from ical order by date'
    rows = query_db(sql)
    args = []
    m = None
    previd = None
    for r in rows:
        try:
            d = CN_DAY[r['lunardate']]
        except KeyError:
            #print 'debug: %s %s' % (r['date'], r['lunardate'])
            m = CN_MON[r['lunardate']]
            d = 1

        if not m:
            continue

        if m == 12 and d == 8:
            args.append((r['id'], u'腊八'))
        elif m == 1 and d == 1:
            args.append((r['id'], u'春节'))
            args.append((previd, u'除夕'))
        elif m == 1 and d == 15:
            args.append((r['id'], u'元宵'))
        elif m == 5 and d == 5:
            args.append((r['id'], u'端午'))
        elif m == 7 and d == 7:
            args.append((r['id'], u'七夕'))
        elif m == 7 and d == 15:
            args.append((r['id'], u'中元'))
        elif m == 8 and d == 15:
            args.append((r['id'], u'中秋'))
        elif m == 9 and d == 9:
            args.append((r['id'], u'重阳'))
        elif m == 10 and d == 15:
            args.append((r['id'], u'下元'))

        if r['jieqi'] == u'清明':
            args.append((previd, u'寒食'))
        previd = r['id']

    sql_update = 'update ical set holiday=? where id=?'
    conn = sqlite3.connect(DB_FILE)
    db = conn.cursor()
    for arg in args:
        db.execute(sql_update, (arg[1], arg[0]))
        print 'update %s' % arg[1]
    conn.commit()
    print 'Chinese Traditional Holiday updated'


def main():
    cy = datetime.today().year
    start = '%d-01-01' % (cy - 1)
    end = '%d-12-31' % (cy + 1)

    helpmsg = ('Usage: lunar_ical.py --start=startdate --end=enddate\n'
'Example: \n'
'\tlunar_ical.py --start=2013-10-31 --end=2015-12-31\n'
'Or,\n'
'\tlunar_ical.py without option will generate the calendar from previous year '
'to the end of the next year')

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'h',
                                   ['start=', 'end=', 'help'])
    except getopt.GetoptError as err:
        print str(err)
        print helpmsg
        sys.exit(2)
    hkstart = datetime.strptime('1901-01-01', '%Y-%m-%d')
    hkend = datetime.strptime('2100-12-31', '%Y-%m-%d')
    for o, v in opts:
        if o == '--start':
            start = v
            if datetime.strptime(start, '%Y-%m-%d') < hkstart:
                sys.exit('start date must newer than 1901-01-01')
        elif o == '--end':
            end = v
            if datetime.strptime(end, '%Y-%m-%d') > hkend:
                sys.exit('end date must before 2100-12-31')
        elif 'h' in o:
            sys.exit(helpmsg)

    if not os.path.exists(DB_FILE):
        initdb()
        update_cal()
        post_process()  # fix error in HK data
        update_holiday()
    if len(sys.argv) == 1:
        fp = OUTPUT % ('prev_year', 'next_year')
    else:
        fp = OUTPUT % (start, end)

    gen_cal(start, end, fp)


if __name__ == "__main__":
    main()
