# -*- coding: utf-8 -*-
import timeout_decorator
import numpy as np
class RSP_Agent_1:
    def __init__(self,num_match=10000):
        self.cnt = 0  # カウンター（今の相手と何回対戦したか）
        self.p0 = 0.05  # probability of "Rock"
        self.p1 = 0.9  # probability of "Scisors"
        self.p2 = 1-self.p0-self.p1  # probability of "Paper"
        self.num_match = num_match  # 何回対戦するか
        self.oppo_hands = []  # 相手の手を記憶する
        self.my_hands = []  # 自分の手を記憶する
    @timeout_decorator.timeout(1)  # このdecoratorを忘れない
    def output_hand(self):
        # time.sleep(3)
        # self.my_hands,self.oppo_handsを使ってこの関数をうまく作ることになる
        a = np.random.rand()
        if a<=self.p0:
            self.my_hands.append(0)
            return 0
        elif a<=self.p0+self.p1:
            self.my_hands.append(1)
            return 1
        else:
            self.my_hands.append(2)
            return 2
    def get_hand(self,x):
        self.cnt += 1
        self.oppo_hands.append(x)

class RSP_Agent_2:
    def __init__(self,num_match=10000):
        self.cnt = 0  # カウンター（今の相手と何回対戦したか）
        self.p0 = 0.05  # probability of "Rock"
        self.p1 = 0.9  # probability of "Scisors"
        self.p2 = 1-self.p0-self.p1  # probability of "Paper"
        self.num_match = num_match  # 何回対戦するか
        self.oppo_hands = []  # 相手の手を記憶する
        self.my_hands = []  # 自分の手を記憶する
    @timeout_decorator.timeout(1)  # このdecoratorを忘れない
    def output_hand(self):
        # time.sleep(3)
        # self.my_hands,self.oppo_handsを使ってこの関数をうまく作ることになる
        a = np.random.rand()
        if a<=self.p0:
            self.my_hands.append(0)
            return 0
        elif a<=self.p0+self.p1:
            self.my_hands.append(1)
            return 1
        else:
            self.my_hands.append(2)
            return 2
    def get_hand(self,x):
        self.cnt += 1
        self.oppo_hands.append(x)

class RSP_Agent_3:
    def __init__(self,num_match=10000):
        self.cnt = 0  # カウンター（今の相手と何回対戦したか）
        self.p0 = 0.05  # probability of "Rock"
        self.p1 = 0.9  # probability of "Scisors"
        self.p2 = 1-self.p0-self.p1  # probability of "Paper"
        self.num_match = num_match  # 何回対戦するか
        self.oppo_hands = []  # 相手の手を記憶する
        self.my_hands = []  # 自分の手を記憶する
    @timeout_decorator.timeout(1)  # このdecoratorを忘れない
    def output_hand(self):
        # time.sleep(3)
        # self.my_hands,self.oppo_handsを使ってこの関数をうまく作ることになる
        a = np.random.rand()
        if a<=self.p0:
            self.my_hands.append(0)
            return 0
        elif a<=self.p0+self.p1:
            self.my_hands.append(1)
            return 1
        else:
            self.my_hands.append(2)
            return 2
    def get_hand(self,x):
        self.cnt += 1
        self.oppo_hands.append(x)
        