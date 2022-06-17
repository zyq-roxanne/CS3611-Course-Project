# coding : utf-8
import socket, threading, sys, time, select, os
from Cache import Cache

# 多线程的代理服务器
def serve(tcpSerPort = 12000):
    '''
    A multithread HTTP proxy server based on HTTP 1.1
    Notice that the server can only handle http headers but not https
    '''
    try:
        # 初始化一个服务器上的套接字
        tcpSerSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # 绑定，监听
        tcpSerSock.bind(('', tcpSerPort)) # 默认绑定127.0.0.1
        tcpSerSock.listen(1024) # 这里虽然监听了1024个，实际上只有一个线程，表示的实际含义是最大连接客户机数量为1024
        webcache = Cache(1000) # 模拟代理服务器本地的存储空间

        t = threading.Thread(target=thread_server, args=(tcpSerSock, webcache))
        t.setDaemon(True)
        t.start()
        while True:
            time.sleep(999)
    
    except KeyboardInterrupt:
        print('Interrupt by Keyboard')
        print('exit..')

    finally:
        tcpSerSock.close()

def thread_server(tcpSerSock:socket.socket, cache):
    '''
    A multithread HTTP proxy server

    Parameters
    ----------
    tcpSerSock : socket in proxy server
    cache : Web cache
    '''
    while True:
        tcpCliSock, addr = tcpSerSock.accept() # 建立到客户端套接字的tcp连接
        tcpCliSock.settimeout(60)
        t = threading.Thread(target = thread_proxy, args = (tcpCliSock, addr, cache))
        t.setDaemon(True)
        t.start()

def thread_proxy(tcpCliSock : socket.socket, addr, cache):
    '''
    Parse client requests

    Parameters
    ----------
    tcpCliSock : socket in client host
    addr : request add
    cache : Web cache
    '''
    t_name = threading.currentThread().name

    print('{}---- Received a connection from {}'.format(t_name, addr))

    # get request parse header
    request = tcpCliSock.recv(4096).decode()
    request_header = split_header(request)
    # print(request)

    if len(request_header) > 4096 - 11:
        tcpCliSock.close()
        raise OverflowError('Request Header is too long!')
        return
    
    if not request_header:
        tcpCliSock.close()
        return
    
    fields = parse_header(request_header)

    filename = fields['path']
    if find_cache(filename, tcpCliSock, cache):
        return

    raw_host = fields['Host']
    if not raw_host:
        print('Stupid Proxy cannot parse Host') # 无法解析host
        print('{}---- request header: {}'.format(t_name, request_header))
        tcpCliSock.close()
        return
    # 解析成功
    hostSock, hostPort = parse_host(raw_host)
    hostPort = int(hostPort)

    # Entity body
    if len(request_header) < len(request) - 4 and 'Content-length' in fields.keys: #非空，针对POST方式的request
        content_length = fields['Content-length']
        request = get_entity(tcpCliSock, request, len(request_header) + 4 + int(content_length))

    proxySock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # 这个套接字与host交互来获得网页
    proxySock.connect((hostSock, hostPort))
    proxySock.settimeout(60)

    # 发送请求报文 + 获得响应报文，这里https和http的处理方式不同
    
    # 判断是否为CONNECT

    flag = False

    if fields['method'] == 'CONNECT':
        flag = True
    
    if not flag:
        proxySock.sendall(request.encode())
        send_response(proxySock, tcpCliSock, filename, cache)
    else:
        send_https_response(proxySock, tcpCliSock)
        send_response(proxySock, tcpCliSock, filename, cache)

    tcpCliSock.close()
    proxySock.close()

def split_header(request : str):
    '''
    Get header from the request message
    '''
    i, l = 3, len(request)
    while i<l and (request[i] != '\n' or request[i-3:i+1] != '\r\n\r\n'):
        i+= 1
    return request[:i-3]

def parse_header(header): #从header中获得字段信息
    '''
    Parse header to get message in header
    
    Parameters
    ----------
    header : the raw header

    Returns
    ----------
    fields : message stored in dict
    '''
    base, l = 0, len(header)
    fields = dict()
    i = header.find('\n') - 1
    firstline = header[base: i]
    fields['method'], fields['path'], fields['version'] = firstline.split()
    base = i + 1
    while i < l:
        if header[0] == '\r' and 0 < l-1 and header[1] == '\n':
            break
        while i<l and header[i] != ':':
            i += 1
        if i < l:
            name = header[base:i].strip()
            base = i + 1
            while i < l and not (header[i] == '\n' and header[i-1] =='\r' ):
                i += 1
            value = header[base:i-1].strip()
            fields[name] = value
            base = i + 1
    return fields


def parse_host(raw : str):
    '''
    Parse host to get host socket and port

    Parameters
    ----------
    raw : raw Host string

    Returns
    -------
    Host : host IP address
    port : host port
    '''
    for i in range(len(raw)):
        if raw[i] == ':':
            return raw[:i].strip(), raw[i+1:].strip()
    return raw.strip(), '80' # 默认端口为80

def get_entity(Sock, message, length):
    '''
    receive body to get a full header
    '''
    if length == -1:
        while message[-5:] != '\r\n0\r\n\r\n' :
            message += Sock.recv(4096) 
    else:
        while len(message) < size :
            message += Sock.recv(4096)
    return message

def find_cache(filename, tcpCliSock, cache: Cache):
    '''
    Send cache to client if file exits
    
    Parameters
    ---------
    filename : name of request file
    tcpCliSock : client socket for response
    Cache : Web cache

    Returns
    -------
    Exist : True if file exits else False
    '''
    if filename in cache:
        return False
        for data in cache.get(filename):
            tcpCliSock.send(data)
        print('Read from cache')
    else:
        return False

def write_cache(filename, data_list, cache: Cache):
    cache.update(filename, data_list)

def send_response(proxySock, tcpCliSock, filename, cache):
    '''
    Send the server's response to client

    Parameters
    ----------
    proxySock : server socket
    tcpCliSock : client socket
    filename : file name of cache
    cache : Web cache
    '''
    while True:
        data = ''
        data_list = []
        # 这里用select实现了端到端直传，从而让客户端和服务器自行判断是否结束，是http2.0的持久连接功能
        (rlist, wlist, elist) = select.select([proxySock], [], [], 3)
        if rlist:
            data = rlist[0].recv(4096)
            data_list.append(data)
            if len(data) > 0:
                tcpCliSock.send(data)
            else:
                break
            write_cache(filename, data_list, cache)

def send_https_response(proxySock, tcpCliSock):
    '''
    Send the server's response in https to client

    Parameters
    ----------
    proxySock : server socket
    tcpCliSock : client socket
    '''
    data = b"HTTP/1.0 200 Connection Established\r\n\r\n"
    tcpCliSock.sendall(data)
    # communicate(tcpCliSock, proxySock)
    t = threading.Thread(target=communicate, args = (tcpCliSock, proxySock))
    t.setDaemon(True)
    t.start()


def communicate(sock1, sock2):
    '''
    Communication between two sockets

    Parameters
    ----------
    sock1 : socket
    sock2 : socket
    '''
    try:
        while True:
            data = sock1.recv(4096)
            if not data:
                return
            sock2.sendall(data)
    except:
        pass

if __name__ == '__main__':
    try:
        print('start server')
        serve()

    except Exception as e:
        print('error exit..')
    
    finally:
        print('end server')
    sys.exit(0)