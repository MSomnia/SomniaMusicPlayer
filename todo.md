系统层

* [X]  底部控制栏在歌曲名称和作者下面加一个音源平台，文字显示为对应颜色：spotify绿色，网易云音乐用橙色，youtube用红色。
* [X]  设置界面各平台登录的账户名显示以及退出登录功能和登录功能
* [X]  “主页“以及“我的库“中的列表和歌曲是否有办法不要每次进入都重新加载。是否有办法缓存，只有在内容有变动时再重新加载
* [X]  鼠标移动到歌曲上时最右侧添加“加入到播放列表“按钮
* [X]  待播列表不要做成弹出窗口，改为弹出列表，当鼠标点击app其他位置时自动关闭待播列表。
* [X]  在首页的列表中和我的库的歌曲列表中点击一首歌时，应当把list其他的歌也都加入待播列表。
* [X]  当歌曲因为各种原因无法播放时，显示一个弹窗“歌曲无法播放“，这个弹窗应在3秒后消失。并且自动切换列表中的下一首歌。
* [X]  当一首歌播完并且待播列表为空时，自动推荐播放新歌。
* [X]  自定义背景图
* [X]  搜索页，首页，我的库，和待播列表页这四个页面显示歌曲的格式改为用固定宽度的表格：歌曲名称 | 歌手 | 时长
* [X]  制作歌手相关页，其中显示该歌手的歌曲。歌手相关页可以从左下角控制栏的歌手名称或页内歌曲词条中的歌手名进入。根据当前歌曲所属平台获取歌手相关信息和歌曲。
* [X]  搜索页中如果有搜索到符合的专辑，在列表最上显示专辑名及专辑图
* [X]  专辑页面添加“全部播放“按钮。将专辑内所有歌曲加入空的待播列表。
* [X]  将“我的库“页面中三个平台显示歌单的功能迁移至侧边栏“平台账号“内。操作逻辑为，如果某个平台账号没有登录，则点击触发已有的登录程序。若已经登录，则显示该音乐平台的“我的库“。
* [X]  在底部控制栏以及搜索页面和主页歌曲添加“加入歌单“功能。根据当前操作歌曲的来源，弹出加入对应平台的用户歌单。
* [X]  在各种位置的歌曲词条中加入歌曲图，放在歌名之前。不同位置的图应适应不同组件的大小。
* [X]  做一个“待机页“。进入通道为点击侧边栏上方的用户名。整个待机页应当占据整个app，只保留下方控制栏。页面内容：背景为用户在设置界面设置的背景图，如果没有设置背景图，则使用默认的黑色。页面左半部分从上到下显示当前播放的歌曲的封面图，歌名，作者，滚动歌词。右半部分先使用文字占位符设计。
* [X]  设置界面退出账号按钮增加一个二级确认按钮以防误触。
* [X]  提前加载列表下一首歌，以防止两首歌切换时黑掉几秒钟。
* [X]  启动app后所以页面第一次加载太慢，是否可以进行页面内容预加载以提升用户体验？
* [ ]  添加当前歌单随机播放功能
* [X]  加歌单时先弹出一个列表，如果歌单还没获取时，先显示“加载歌单中“，歌单获取后填充这个歌单，以免用户在点击了按钮后没有即时反馈。
* [ ]  在搜索页，为三个平台加入搜索历史功能，以及清除历史记录按钮。
* [X]  在三个平台的我的库的音乐歌单的单曲加入“从歌单移出“功能

Mac OS

* [ ]  macos 顶部状态栏歌曲显示
* [X]  接入macos系统媒体播放管线，也即macos的系统媒体控制能抓取到app音乐播放情况和进行控制。
* [ ]  编辑macos系统状态栏左上角菜单内容。
* [X]  设计app icon。
* [ ]  设计自动接收更新功能
* [ ]  app最上方系统控制栏的app名称显示组件可以整个去掉吗？

ui层

* [X]  隐藏所有列表的左右滑动栏slider，优化上下滑动栏slider样式为椭圆形窄slider。
* [X]  歌词界面背景为音乐封面图，50%虚化。
* [X]  当前搜索，首页，和我的库界面中的三个平台切换按钮被再次点击时会切换回白色，应当在再次被点击时保留原色。以及，这些按钮在没有被选中时，按钮样式应当为：白色边框，白色文字，透明背景。
* [X]  侧边栏平台账号指示灯和文字，spotify保持绿色，网易云音乐用橙色，youtube用红色。
* [X]  搜索，首页，和我的库界面中的三个平台切换按钮的背景色：spotify保持绿色，网易云音乐用橙色，youtube用红色。
* [X]  首页界面，让内容填充整个界面（比如只有一个列表的话，这个列表应当填充页面到底部；有多个列表应当合理安排每个的大小）
* [X]  底部控制栏中歌曲信息区域（歌名，歌手信息，图片）的宽度设置为固定与侧边栏同宽。
* [X]  设置界面中的循环模式功能和随机播放功能移动到底部控制栏。
* [X]  播放队列显示剩余歌曲数量
* [X]  我想要让这个app ui分为三部分：左侧侧边栏，右侧显示页，底部控制栏。整个app背景颜色为黑色，侧边栏和显示页背景色为当前的灰色，底部控制栏保持为黑色。侧边栏和显示页不应该完全贴合app左侧和右侧，而是留出一些空间，露出app背景的黑色，从而提升视觉分区效果。同时，侧边栏和显示页中间也要留一些gap，漏出背景黑色。
* [X]  控制栏音量控制和设置界面音量控制未同步，修复。
* [ ]  控制栏左侧歌曲图，只有左侧两个角是圆角，右侧两个角是直角。我需要全部都是圆角处理。修复。
* [X]  按键控制：当目前控制不在app内任何输入框时，空格控制播放/暂停。
* [X]  所有位置的歌曲图的清晰度好像都有点低。不知道是不是因为缩小导致的压缩，有办法在缩小fit组件大小时依旧保持清晰吗？





一段时间没操作app后有概率log会打印以下内容，排查并修复。
Failed reading packet! Failed to receive packet
Exception in thread session-packet-receiver:
Traceback (most recent call last):
File "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/librespot/crypto.py", line 58, in receive_encoded
header_bytes = self.__receive_cipher.decrypt(connection.read(3))
^^^^^^^^^^^^^^^^^^
File "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/librespot/core.py", line 1933, in read
return self.__socket.recv(length)
^^^^^^^^^^^^^^^^^^^^^^^^^^
ConnectionResetError: [Errno 54] Connection reset by peer

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
File "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/librespot/core.py", line 2036, in run
packet = self.__session.cipher_pair.receive_encoded(
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/librespot/crypto.py", line 69, in receive_encoded
raise RuntimeError("Failed to receive packet")
RuntimeError: Failed to receive packet

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
File "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/threading.py", line 1075, in _bootstrap_inner
self.run()
File "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/threading.py", line 1012, in run
self._target(*self._args, **self._kwargs)
File "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/librespot/core.py", line 2049, in run
self.__session.reconnect()
File "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/librespot/core.py", line 1246, in reconnect
self.connection = Session.ConnectionHolder.create(
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
File "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/librespot/core.py", line 1910, in create
sock.connect((ap_address, ap_port))
ConnectionRefusedError: [Errno 61] Connection refused
