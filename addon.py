import sys
import xbmc
import xbmcgui
import urllib
import urllib2
import xbmcplugin
import xbmcaddon
import json
import re
from datetime import datetime, timedelta
import time
 
addon_handle = int(sys.argv[1])
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
MEDIA_URL = xbmc.translatePath('special://home/addons/{0}/resources/media/'.format(ADDON_ID))
SESSION = ADDON.getSetting("session")
FORMAT_LIVE = 'm3u8'
FORMAT_TIMESHIFT = 'm3u8'

# cache
try:
   import StorageServer
except:
   import storageserverdummy as StorageServer
CACHE = StorageServer.StorageServer("sledovanitv", 1)

channelNames = None


class LoginWindow(xbmcgui.WindowDialog):
    def __init__(self, message):
        offsetX = 300
        offsetY = 200
        self.background = xbmcgui.ControlImage(x=offsetX, y=offsetY, width=700, height=300, filename=MEDIA_URL + "background.jpg")

        self.login = xbmcgui.ControlEdit(x=0, y=0, width=400, height=35, label="")
        self.login.setPosition(offsetX + 200, offsetY + 100)
        self.login.setWidth(400)
        self.login.setHeight(35)

        self.password = xbmcgui.ControlEdit(x=0, y=0, width=400, height=35, label="", isPassword=1)
        self.password.setPosition(offsetX + 200, offsetY + 150)
        self.password.setWidth(400)
        self.password.setHeight(35)

        self.ok = xbmcgui.ControlButton(x=offsetX + 200, y=offsetY + 200, width=300, height=35, label=translation(30022))

        self.addControl(self.background)
        self.addControl(xbmcgui.ControlLabel(x=offsetX + 50, y=offsetY + 50, width=600, height=35, label=message))
        self.addControl(xbmcgui.ControlLabel(x=offsetX + 50, y=offsetY + 100, width=150, height=35, label=translation(30020)))
        self.addControl(xbmcgui.ControlLabel(x=offsetX + 50, y=offsetY + 150, width=150, height=35, label=translation(30021)))
        self.addControl(self.login)
        self.addControl(self.password)
        self.addControl(self.ok)

        self.setFocus(self.login)
        self.login.controlDown(self.password)
        self.password.controlUp(self.login)
        self.password.controlDown(self.ok)
        self.ok.controlUp(self.login)

        self.resultLogin = ""
        self.resultPassword = ""
        

    def onControl(self, control):
        if control == self.ok:
            self.close()
            self.resultLogin = self.login.getText()
            self.resultPassword = self.password.getText() 
# end LoginWindow


def mainMenu():
    xbmc.executebuiltin("Container.SetViewMode(500)")
    addDir(translation(30002), "", "live", MEDIA_URL + "live.png")
    addDir(translation(30009), "", "radio", MEDIA_URL + "radio.png")
    addDir(translation(30004), "", "pvr", MEDIA_URL + "pvr.png")
    addDir(translation(30005), "", "search", MEDIA_URL + "search.png")
    addDir(translation(30006), "", "settings", MEDIA_URL + "settings.png")
    xbmcplugin.endOfDirectory(addon_handle)


def pvrMenu():
    response = apiCall("get-pvr")
    mode = "playPvr"

    if isSuccess(response):
        xbmc.executebuiltin("Container.SetViewMode(51)")

        for record in response["records"]:
            u = sys.argv[0] + "?url=" + str(record["id"]) + "&mode=" + urllib.quote_plus(mode)

            title = record["title"] + " (" + getChannelName(record['channel']) + ", " + formatDate(record['startTime']) + ")"

            item = xbmcgui.ListItem(unicode(title))
            item.setInfo(type="Video", infoLabels={ "dateadded": record['created'] })
            item.setProperty('IsPlayable', 'true')
            item.addStreamInfo("video", {"duration": record['eventDuration']})
            xbmcplugin.addDirectoryItem(handle=addon_handle, url=u, listitem=item, isFolder=False)

        xbmcplugin.endOfDirectory(addon_handle)
    else:
        showError(translation(30031))
        print "FAILED TO LOAD PVR"


def getPlaylist():
    value = getCache("playlist")
    if value:
        return eval(value)

    response = apiCall("playlist", {'format': FORMAT_LIVE})

    if isSuccess(response):
        channels = response['channels']
        setCache("playlist", repr(channels), 3600)
        return channels
    else:
        print "FAILED TO LOAD PLAYLIST"


def getEpg():
    value = getCache("epg")
    if value is not None:
        return eval(value)

    response = apiCall("epg", {'time': getTime().strftime("%Y-%m-%d %H:%M"), 'duration': 180})

    if isSuccess(response):
        channels = response['channels']
        newChannels = {}

        for channel in channels:
            newList = []
            list = channels[channel]
            for event in list:
                try:
                    parsedEvent = {'title': event['title'], 'start': parseTime(event['startTime']).strftime("%Y-%m-%d %H:%M:%S"), 
                            'end': parseTime(event['endTime']).strftime("%Y-%m-%d %H:%M:%S"), 'avail': event['availability']}
                    newList.append(parsedEvent)
                except ValueError:
                    # ignore bad events
                    pass

            newChannels[channel] = newList

        setCache("epg", repr(newChannels), 7200)
        return newChannels
    else:
        print "FAILED TO LOAD EPG"


def flushCache():
    CACHE.delete("playlist")
    CACHE.delete("epg")


def getCache(key):
    value = CACHE.get(key)
    if value:
        expiration = CACHE.get(key + "_expiration")
        if not expiration:
            return None
        expiration = parseTime(expiration)
        if expiration and expiration >= datetime.now():
            return value
    return None


def setCache(key, value, lifetime):
    CACHE.set(key, value)
    CACHE.set(key + "_expiration", (datetime.now() + timedelta(seconds=lifetime)).strftime("%Y-%m-%d %H:%M:%S"))


def getChannelName(id):
    global channelNames
    if channelNames:
        return channelNames.get(id, id)

    playlist = getPlaylist()
    if not playlist:
        return id

    channelNames = {}
    for channel in playlist:
        channelNames[channel['id']] = channel['name']

    return channelNames.get(id, id)


def liveMenu(showType):
    mode = "playLive"

    channels = getPlaylist()
    epg = getEpg()
    now = getTime()

    if channels:
        #xbmc.executebuiltin("Container.SetViewMode(500)")
        for channel in channels:
            if channel['type'] == showType:
                eventTitle = ""
                if channel['id'] in epg:
                    event = getEvent(now, epg[channel['id']])
                    if event is not None:
                        eventTitle = "   |  " + event['title']

                u = sys.argv[0] + "?url=" + urllib.quote_plus(channel['url']) + "&mode=" + urllib.quote_plus(mode)
                item = xbmcgui.ListItem(unicode("[B][COLOR white]" + channel["name"] + "[/COLOR][/B]" + eventTitle), 
                        iconImage=channel["logoUrl"], thumbnailImage=channel["logoUrl"])
                item.setProperty('IsPlayable', 'true')
                xbmcplugin.addDirectoryItem(handle=addon_handle, url=u, listitem=item, isFolder=False)

        xbmcplugin.endOfDirectory(addon_handle)
    else:
        showError(translation(30030))


def getEvent(now, eventList):
    for event in eventList:
        if parseTime(event['end']) > now:
            return event
    return None


def search(query):
    keyboard = xbmc.Keyboard('', translation(30007))
    keyboard.doModal()
    mode = "playTimeshift"

    if keyboard.isConfirmed() and keyboard.getText():
        query = keyboard.getText()
        response = apiCall('epg-search', {'query': query, 'count': 20})
        if isSuccess(response):
            xbmc.executebuiltin("Container.SetViewMode(51)")

            for event in response['events']:
                u = sys.argv[0] + "?url=" + urllib.quote_plus(event['eventId']) + "&mode=" + urllib.quote_plus(mode)

                playable = canPlayEvent(event)
                title = event["title"] + " (" + getChannelName(event['channel']) + ", " + formatDate(event['startTime']) + ")"
                if playable:
                    title = "[B]" + title + "[/B]"
                else:
                    title = "[I]" + title + "[/I]"

                item = xbmcgui.ListItem(unicode(title))
                item.setProperty('IsPlayable', 'true')
                item.addStreamInfo("video", {"duration": event['duration']})
                xbmcplugin.addDirectoryItem(handle=addon_handle, url=u, listitem=item, isFolder=False)
            xbmcplugin.endOfDirectory(addon_handle)
        else:
            print "SEARCH FAILED"


def settingsMenu():
    deviceId = ADDON.getSetting("deviceId")

    if deviceId:
        addDir(translation(30008), "", "unpair")
    #addDir("Logout", "", "logout", "")
    xbmcplugin.endOfDirectory(addon_handle)


def canPlayEvent(event):
    avail = event.get('availability', 'none')
    if avail == 'timeshift' or avail == 'pvr':
        startTime = parseTime(event['startTime'])
        return startTime < getTime()
    else:
        return False


def formatDate(date):
    parsed = parseTime(date)
    return parsed.strftime("%d.%m. %H:%M")


def parseTime(string):
    #print "Parsing " + string
    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]

    for format in formats:
        try:
            try:
                return datetime.strptime(string, format)
            except TypeError:
                return datetime(*(time.strptime(string, format)[0:6]))
        except ValueError:
            continue

    raise ValueError("Cannot parse datetime" + string)


def getTime():
    return datetime.now()



class NoRedirect(urllib2.HTTPRedirectHandler):
    def http_error_302(self, req, fp, code, msg, headers):
        infourl = urllib.addinfourl(fp, headers, req.get_full_url())
        infourl.status = code
        infourl.code = code
        return infourl

    http_error_303 = http_error_302


def videoHandler(url):
    #print "HANDLE: " + url

    noredirOpener = urllib2.build_opener(NoRedirect())
    urllib2.install_opener(noredirOpener)
    request = urllib2.Request(url)
    response = urllib2.urlopen(request)

    redirect = response.info().getheader('Location')
    #print "REDIRECT: " + str(redirect)
 
    listitem = xbmcgui.ListItem(path=redirect)
    xbmcplugin.setResolvedUrl(addon_handle, True, listitem)

    #player = TimeshiftPlayer()
    #player.duration = 35 * 60

    #player.play(redirect)
    #while player.running:
    #    xbmc.sleep(100)

    #del player


def pvrHandler(id):
    #print "Handling record " + str(id)
    response = apiCall("record-timeshift", {'recordId': id, 'format': FORMAT_TIMESHIFT})
    if isSuccess(response):
        url = response["url"]
        videoHandler(url)
    else:
        showError(translation(30032))
        print "FAILED TO PLAY RECORD"


def timeshiftHandler(eventId):
    #print "Handling timeshift " + str(eventId)
    response = apiCall("event-timeshift", {'eventId': eventId, 'format': FORMAT_TIMESHIFT})
    if isSuccess(response):
        url = response["url"]
        videoHandler(url)
    else:
        showError(translation(30032))
        print "FAILED TO PLAY TIMESHIFT"


def loginDialog():
    error = translation(30023)

    while True:
        window = LoginWindow(error)
        window.doModal()
        if window.resultLogin != "":
            macAddress = xbmc.getInfoLabel('Network.MacAddress')
            friendlyName = xbmc.getInfoLabel('System.FriendlyName')
            response = apiCall("create-pairing", {"username": window.resultLogin, "password": window.resultPassword, 'type': 'xbmc', 'product': friendlyName, 'serial': macAddress})

            if isSuccess(response):
                print "Pairing created"
                ADDON.setSetting("deviceId", str(response['deviceId']))
                ADDON.setSetting("password", str(response['password']))
                return login()
            elif getError(response) != "bad login":
                return False

            error = translation(30024)
        else:
            return False


def login():
    deviceId = ADDON.getSetting("deviceId")
    password = ADDON.getSetting("password")

    if deviceId and password:
        response = apiCall("device-login", {"deviceId": deviceId, "password": password})
        if isSuccess(response):
            global SESSION
            SESSION = response["PHPSESSID"]
            ADDON.setSetting("session", str(SESSION))
            print "Successfully logged"
            return True
        elif getError(response) == "bad login":
            return loginDialog()
        else:
            ADDON.setSetting("session", "")
            print "CANNOT LOGIN"
            return False
    else:
        return loginDialog()


def logout():
    flushCache()
    if SESSION:
        response = apiCall("logout")
        if isSuccess(response):
            print "Logged out"
        ADDON.setSetting("session", "")


def unpair():
    logout()
    deviceId = ADDON.getSetting("deviceId")
    if deviceId:
        apiCall("delete-pairing")



class TimeshiftPlayer(xbmc.Player):
    def __init__ (self):
        xbmc.Player.__init__(self)
        self.running = True
        self.noseek = True
        self.duration = None

    def onPlayBackStarted(self):
        print ">>>> PLAYBACK STARTED <<<<"
        self.noseek = False

    def onPlayBackEnded(self):
        print ">>>> PLAYBACK STOPPED <<<<"
        self.running = False

    def onPlayBackSeek(self, time, seekOffset):
        print ">>>> SEEKED " + str(time) + " <<<<"
        if not self.noseek and self.duration is not None:
            position = int(time * self.duration / 60000)
            positionUrl = re.sub(r'position=\d+', 'position=' + str(position), self.getPlayingFile())
            self.play(positionUrl)


def addDir(name, url, mode, iconimage=""):
    u = sys.argv[0] + "?url=" + urllib.quote_plus(url) + "&mode=" + urllib.quote_plus(mode)
    liz = xbmcgui.ListItem(unicode(name), iconImage=iconimage, thumbnailImage=iconimage)
    liz.setInfo(type="Video", infoLabels={ "Title": name })
    ok = xbmcplugin.addDirectoryItem(handle=addon_handle, url=u, listitem=liz, isFolder=True)
    return ok


def getUrl(url):
    req = urllib2.Request(url)
    #req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 6.1; rv:22.0) Gecko/20100101 Firefox/22.0')
    response = urllib2.urlopen(req)
    link = response.read()
    response.close()
    return link


def apiCall(function, parameters={}):
    query = urllib.urlencode(parameters)
    global SESSION
    
    for x in range(0, 3):
        #print "session: " + str(SESSION)
        url = "http://sledovanitv.cz/api/" + function
        if SESSION:
            url = url + "?PHPSESSID=" + urllib.quote_plus(SESSION) + "&" + query
        else:
            url = url + "?" + query
        print "API: " + url
        content = getUrl(url)
        response = json.loads(content)

        if getError(response) == "not logged":
            if not login():
                return response
        else:
            return response


def parametersToDict(parameters):
    paramDict = {}
    if parameters:
        paramPairs = parameters[1:].split("&")
        for paramsPair in paramPairs:
            paramSplits = paramsPair.split('=')
            if (len(paramSplits)) == 2:
                paramDict[paramSplits[0]] = paramSplits[1]
    return paramDict


def isSuccess(response):
    return response and response.get("status", 0) == 1


def getError(response):
    if isSuccess(response):
        return None
    return response.get("error", "unknown")


def translation(id):
    return ADDON.getLocalizedString(id)


def showError(message):
    xbmc.executebuiltin('XBMC.Notification(Info:,' + message + ',5000)')


params = parametersToDict(sys.argv[2])
mode = urllib.unquote_plus(params.get('mode', ''))
url = urllib.unquote_plus(params.get('url', ''))

#flushCache()

if mode == None:
    mainMenu()
elif mode == "live":
    liveMenu("tv")
elif mode == "radio":
    liveMenu("radio")
elif mode == "pvr":
    pvrMenu()
elif mode == "login":
    login()
elif mode == "settings":
    settingsMenu()
elif mode == "unpair":
    unpair()
elif mode == "playLive":
    videoHandler(url)
elif mode == "playPvr":
    pvrHandler(url)
elif mode == "playTimeshift":
    timeshiftHandler(url)
elif mode == "search":
    search(url)
else:
    mainMenu()
 
