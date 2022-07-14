# import time
# from multiprocessing import Process, Manager
#
# def f(d, l):
#     d[1] = '1'
#     d['2'] = 2
#     d[0.25] = None
#     l.reverse()
#     time.sleep(5)
#     # print('lili')
#
# if __name__ == '__main__':
#     with Manager() as manager:
#         d = manager.dict()
#         l = manager.list(range(10))
#
#         p = Process(target=f, args=(d, l))
#         p.start()
#         p.join()
#
#         print(d)
#         print(l)
#         print("John")
#         # time.sleep(8)


# from multiprocessing import Process
#
#
# def print_func(continent='Asia'):
#     print('The name of continent is : ', continent)
#
# if __name__ == "__main__":  # confirms that the code is under main function
#     names = ['America', 'Europe', 'Africa']
#     procs = []
#     proc = Process(target=print_func)  # instantiating without any argument
#     print('John')
#     procs.append(proc)
#     proc.start()
#
#     # instantiating process with arguments
#     for name in names:
#         # print(name)
#         proc = Process(target=print_func, args=(name,))
#         procs.append(proc)
#         proc.start()


    # # complete the processes
    # for proc in procs:
    #     proc.join()
import sys
import time
from multiprocessing import Process
import os

def info(title):
    print(title)
    print('module name:', __name__)
    print('parent process:', os.getppid())
    print('process id:', os.getpid())

def f(name):
    info('function f')
    print('hello', name)
    time.sleep(5)
    print("Ready to Exit")
    sys.exit(0)
    # return 0

if __name__ == '__main__':
    info('main line')
    p = Process(target=f, args=('bob',))
    p.start()
    # p.join()
    print('John')
    print('asdfassfd')
    # p.join()
    print('aLEX')
    time.sleep(10)
    print('Haowen')