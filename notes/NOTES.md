The call to /mole/world gives a 302 to a page that says browser not supported
but it gives us the values we need anyways. Changing the user agent to firefox
makes us get a 400 instead so this will need more tinkering at some point.

login in right now requires sending the COMPASS, SSID, SID, OSID, and HSID
cookies as a JSON object via the `set-cookies` bot command.

Messages events are in a WebPushNotification, which is a
WebPushNotificationEvent.

GetUserPresence: renamed to GetUserStatus
GetMembers: renamed to GetMemberList
PaginatedWorld: renamed to ResyncWorldLite
GetSelfUserStatus: exists
GetGroup: exists
MarkGroupReadstate: only seeing UpdateGroupLastReadTime and UpdateTopicLastReadTime
CreateTopic: exists
CreateMessage: renamed to PostMessage
UpdateReaction: exists
DeleteMessage: exists
EditMessage: exists
SetTypingState: exists
CatchUpUser: exists
CatupUpGroup: exists
ListTopics: Only seeing GetInitialTopicList as well as pagination
ListMessages: Only seeing GetInitialMessageList, GetMessageListPage, GetMessageUpdates

# Sequence

Simplified sequence of calls from the web client.

/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=ogr8ud
/u/0/webchannel/register?ignore_compass_cookie=1
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=A9tNK
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=hlt9W
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=nZ9dd
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=hpZshb
/u/0/webchannel/events
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=ldc3Yd
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=hpZshb
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=TLCT6 /* first mention of the user name */
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=wte1vf
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=PA1enf
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=nZ9dd
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=ir1jD
/u/0/webchannel/events
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=ldc3Yd
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=HtElWb
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=vWUt9
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=qDdlde
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=eCT9Zc
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=RJ8kkf
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=ir1jD
/u/0/webchannel/events
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=vWUt9
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=qL7xZc
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=aQdzwb
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=X1NQAf
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=G9xNb
/u/0/_/DynamiteWebUi/data/batchexecute?rpcids=X1NQAf
/u/0/webchannel/events
/u/0/webchannel/events
/u/0/webchannel/events

Errors:

Invalid fields/data sent to batchexecute get the following response

[["wrb.fr","RTBQkb",null,null,null,[13,null,[["type.googleapis.com/apps.dynamite.v1.web.datakeys.InvalidArgumentDataError",[null,0]]]],"generic"],["di",123],["af.httprm",122,"5452569223111664617",14]]


# RPC ID's

## RJ8kkf

Not sure on this one yet, but the KoP-Zm09CXw does look like a local message id.
I think it might be a typing notification or focus or something.

1680807987724479 is a time stamp for
`Thursday, April 6, 2023 2:06:27.724 PM GMT-05:00 DST`

Req:

```
[[[null,null,null,"1680807987724479",[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,"dm/1bM4JkAAAAE"]]]]
```

Resp:

```
[[[null,["KoP-ZmO9CXw",null,["KoP-ZmO9CXw",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],"1680807987724479",null,[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,"dm/1bM4JkAAAAE"]]]]"
```

## ldc3Yd

Request:

```
[[[["105751002961729238331"],[[1,[3600]],[2,[3600]]]]]]
```

Response:

```
[[[["105751002961729238331","human/105751002961729238331",0],1,[[1,[1680831841,37765000]],[2,[1680831841,37765000]]]]]]
```

## ir1jD

Request:

```
[]
```

Response:

```
[null,null,0]
```

## uQwtvc

Request:

```
[1,[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]]
```

Response:

```
[1680811519567000]
```

## xok6wd

Send when sending the message "bleepo"

Request:

```
["blee",[],["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],["gary.kramlich@gmail.com"]
```

Response:

```
[]
```

## RTBQkb

`/DynamiteWebDataService.DynamiteCreateTopic`

Sent when sending the message "bleepo"

Request:

```
[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],"bleepo",[],"tc43GFv6nBg",[1],null,"tc43GFv6nBg",false,null,[],true]
```

Response:

```
[null,[["tc43GFv6nBg",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680811523142751","0",null,[[null,"tc43GFv6nBg",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],"bleepo",null,null,null,[["bleepo",null,[]]],null,"1680811523142751",null,null,true,false,1680811523142,["tc43GFv6nBg",null,["tc43GFv6nBg",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680811523142751",null,null,null,null,null,null,null,false,null,false,null,1,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],null,null,null,null,0]],null,0,null,"tc43GFv6nBg",null,false,null,"1680811523142751",null,"1680811523142751",null,1680811523142,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680811523142751",true,0,null,false],["1680811523142751","1680808085550413"]]
```

## gXJzNb

Request:
```
["boq_dynamiteuiserver_20230330.05_p1",["WDv0ld","vrGsLd","ldZ6ve","HEeGTb","Wq0kQb","OZ7hjb","xbzdqb","CCLr1e","IT33vd","Addnkf","KlHx2","sNHPIf","Yamd3c","FDGe6b","MqeEOd","DYp3yc","jb8xuc","iJJUzd","xm01Bb","a9sONe","ihxGId","oNYBJd","imwt8e","ND0sJc","YVsT9d","csqZL","tDGFt","V4Xwsd","KPEHac","Po3FB","LnHed","r2Ufwf","EidiL","v7rsQc","xuCeWd","NdrqEb","wehTze","j0DU0b","fttWhe","rOOoYb","UBHcPb","OLs3sb","BwRBs","IiFKpe","o38xyf","rg0ysf","IrNUZc","iW2ju","UNOEKc","b8fMhf","VM5voc","BDvzj","rnyTfc","Md5uwd","MCaMuc","fbR4Ff","MZciB","pkuj8b","E3jKWe","PtUryc","fSj9Le","gPU9Nc","lzODie","p92tDc","KGhXhd","HyMTze","P2YHQb","ziZql","KtCsrf","oRurxd","m0UiD","xY9Jec","xJyyXb","Tyi48e","QhXqJd","iwz7Oe","SJjLb","PLNzRe","xg7lGb","KiRBBc","pkYLwc","C136xe","Ka1bDe","nvIy","Osj2O","lbdkge","L2vvtb","Ps80we","MS6Trf","wLyL4e","pDKMdd","kKYct","dcZ7rc","uDVKB","rm7Skc","jy5zee","NdLPff","tfKSId","DFRCsd","HDEnM","HDiXK","IKVpMb","WrFo6e","phdsNe","qze8F","TJfatc","RjKZLe","EUNFHd","uIs1F","vjWwE","ycE1lc","Zpwl5b","R017Se","R0Wj9","AnFqGb","NA64Td","q37rrc","F9uSx","jL5u4d","Ey8Ksc","n817ce","v3bOFf","I2M5V","v076Qc","WqZfs","bqsgTd","DJegYc","jkJP3d","xmeGFd","GFLFFc","oC4WDe","UvZcsc","qivG0c","Xr9Q1e","WJMzId","RKg7re"]]
```

Response:

```
[false]
```

## MPzotf

`/DynamiteWebDataService.DynamiteGetTopicListPageUp`

Request:

```
[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],"1680125650529631",null,null,1,true,2,null]
```

Response:

```
[[[["FTlOyNBYEHc",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680125625104084","0",null,[[null,"FTlOyNBYEHc",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],"Hiya!",null,null,[[15,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,3]],[["",[0],[]],["Hiya!",null,[]]],null,"1680125625104084",null,null,true,false,1680125625104,["FTlOyNBYEHc",null,["FTlOyNBYEHc",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680125625104084",null,null,null,null,null,null,null,false,null,false,null,1,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1]]],null,0,null,"FTlOyNBYEHc",null,false,null,"1680125625104084",null,"1680125625104084",null,1680125625104,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680125625104084",true,0,null,false],[["sroUG58juH0",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680125637734463","0",null,[[null,"sroUG58juH0",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"how's it going?",null,null,null,[["how's it going?",null,[]]],null,"1680125637734463",null,null,true,false,1680125637734,["sroUG58juH0",null,["sroUG58juH0",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680125637734463",null,null,null,null,null,null,null,false,null,false,null,1,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"sroUG58juH0",null,false,null,"1680125637734463",null,"1680125637734463",null,1680125637734,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680125637734463",true,0,null,false]],10,true,["1680812020956210"],["1680811523604620"]]
```

## pOXmte

Request:

```
[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,null,[]]
```

Response:

```
[2,[[[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],["user/101612323147699054057",null,"101612323147699054057",null,["101612323147699054057","human/101612323147699054057",0],"user/human/101612323147699054057"]],2,3]]]
```

## ogr8ud

Request:

```
[]
```

Response:

```
[[["boq_dynamitedataserver_20230330.13_p1",null,null,"Data",1680221623000],["dynamite.frontend_20230402.14_p0",null,"FRONTEND_PROD","Frontend",1680471405000,204],["dynamite.backend_20230330.12_p0",null,"BACKEND_PROD","Backend",1680212751000,214]]]
```

## A9tNK

Request:

```
[]
```

Response:

```
[]
```

## hlt9W

Request:

```
[]
```

Response:

```
["0"]
```

## nZ9dd

Request:

```
["America/Chicago"]
```

Response:

```
[]
```

## hpZshb

Request:

```
[]
```

Response:

```
[10,50,5,5,20,5,2,10,300,20,20,5,15,20]
```


## TLCT6

`/DynamiteWebDataService.DynamiteGetGroupList`

Request:

So far this is always the request data.

```
[null,[],[],null,true,null,null,[]]
```

This means should be able to request this with the following but needs to be
tested yet as we might need the additional fillers.

```protobuf
message SelfUserRequest {
	optional bool unknown = 5; /* this should be true */
}
```

Response:

There's a couple of envelopes here before the User structure from the old
version.

It looks like something like this so far.

```protobuf
message Envelope1 {
	optional string unknown1 = 1;
	optional string unknown2 = 2;
	optional string unknown3 = 3;
	repeated string timestamps = 4; /* Not sure why this is repeated or a
                                     * string, but it does appear to be a time
                                     * stamp. This one is roughly 8 minutes
                                     * before the request was made, so perhaps
                                     * this is a list of idle times for each
                                     * device the user is connected with?
                                     */
	optional Envelope2 envelop2 = 5;
	optional bool unknown14 = 14;
	repeated DeviceData sessions = 17;
}

message DeviceData {
	optional Platform platform = 1; /* need to test more but this appears to be
	                                 * the platform enum.
	                                 */

	optional string DeviceId = 2;
	optional bool unknown3 = 3; /* might be active or not idle or something */
	optional int64 last_seen = 4; /* not completely sure on this one but it is
	                               * a timestamp.
	                               */
}

message Envelope2 {

}

```
[null,null,null,["1680812258809231"],[[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,"Gary “grim” Kramlich",null,null,null,true,null,"1680812258275247","1680811523142751",null,1,false,1680812258275,null,null,null,[["105751002961729238331","Gary “grim” Kramlich","https://lh3.googleusercontent.com/a-/ACB-R5S5y83wdqP2-0ZDPaKtrGLbOn2MjiBLMQ8P0ncNpg\\u003dk-no-mo","gary.kramlich@gmail.com",null,true,"Gary",1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,[[]],null,null,1,1]],null,["FTlOyNBYEHc",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],["101612323147699054057",null,null,"",null,null,null,null,null,["101612323147699054057","human/101612323147699054057",0],null,null,null,null,null,null,null,3],["101612323147699054057",null,null,null,null,null,null,null,null,["101612323147699054057","human/101612323147699054057",0],null,true,null,null,null,null,null,3],1680125618499,[[[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],["user/101612323147699054057",null,"101612323147699054057",null,["101612323147699054057","human/101612323147699054057",0],"user/human/101612323147699054057"]],2],[[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],["user/105751002961729238331",null,"105751002961729238331",null,["105751002961729238331","human/105751002961729238331",0],"user/human/105751002961729238331"]],2]],false,false,false,"1680812258275247",true,false,[true,1],null,[1],true,null,true,false,1680811523142,[2],null,null,false,null,[["105751002961729238331","Gary “grim” Kramlich","https://lh3.googleusercontent.com/a-/ACB-R5S5y83wdqP2-0ZDPaKtrGLbOn2MjiBLMQ8P0ncNpg\\u003dk-no-mo","gary.kramlich@gmail.com",null,true,"Gary",1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,[[]],null,null,1,1]],null,null,[["5Zp7Bd88JQw",null,["5Zp7Bd88JQw",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],["105751002961729238331","Gary “grim” Kramlich","https://lh3.googleusercontent.com/a-/ACB-R5S5y83wdqP2-0ZDPaKtrGLbOn2MjiBLMQ8P0ncNpg\\u003dk-no-mo","gary.kramlich@gmail.com",null,true,"Gary",1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,[[]],null,null,1,1],[["wheeeeeeeee!",null,[]]],"1680812258275247",null,"1680812258275247",null,null,false,false],null,null,null,null,"0",1,null,0,null,null,6,false,null,true,null,null,"1680125618499312",2,null,3,[],null,null,null,null,null,null,null,null,[[[2,1,2],[0,2,2]]]]],null,null,null,null,null,null,[null,0,null,0],0,true,null,null,-1,[[1,"ChIIr9_azImW_gIQ8N2s1YuC_gI\\u003d",false,1680812258275247]]]
```

### wte1vf

Request:

```
[]
```

Response:

```
[0]
```

## PA1enf

Request:

```
["3150693275562920",[1680812736,874000000]]
```

Response:

```
[]
```

## HtElWb

Request:

```
[[[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],["user/101612323147699054057",null,"101612323147699054057",null,["101612323147699054057","human/101612323147699054057",0],"user/human/101612323147699054057"]]]]
```

Response:

```
[[[[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],["user/101612323147699054057",null,"101612323147699054057",null,["101612323147699054057","human/101612323147699054057",0],"user/human/101612323147699054057"]],[[8,10,12,14,37,15,16,27,18,19,20,34,36,38,21,33,22,35,28,39]]]],["1680812258809231"]]
```

## vWUt9

Request:

```
[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],true,null,null,null,null,null,null,null,null,[1680812739,null]]
```

Response:

```
[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,[[["user/105751002961729238331",null,"105751002961729238331",null,["105751002961729238331","human/105751002961729238331",0],"user/human/105751002961729238331"],["105751002961729238331","Gary “grim” Kramlich","https://lh3.googleusercontent.com/a-/ACB-R5S5y83wdqP2-0ZDPaKtrGLbOn2MjiBLMQ8P0ncNpg\\u003dk-no-mo","gary.kramlich@gmail.com",null,true,"Gary",1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,[[]],null,null,1,1],null,true],[["user/101612323147699054057",null,"101612323147699054057",null,["101612323147699054057","human/101612323147699054057",0],"user/human/101612323147699054057"],["101612323147699054057","Mirg repaer","https://lh3.googleusercontent.com/a/AGNmyxZuyR7oIaHZSLkZr8jDCcKPlGSYyg7DKS8gDilF\\u003dk-no-mo","mirgy04@gmail.com",null,true,"Mirg",1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,[[]],null,null,1,1],null,true]],["1680812258275247"],null,"",null,null,null,null,[0]]
```

## qDdlde

`/DynamiteWebDataService.DynamiteGetInitialTopicList`

Really hoping this is like the PaginatedWorldResponse because this is **HUGE**.

Request:

```
[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,null,null,null,null,null,"1680811523142751",null,null,true,null,null,"0",[1,true,2],null,null,null,1,null,null,null,null]
```

Response:

```
[[[["ClmqQZQXgjs",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680125669985231","0",null,[[null,"ClmqQZQXgjs",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"cool, you too!",null,null,null,[["cool, you too!",null,[]]],null,"1680125669985231",null,null,false,false,1680125669985,["ClmqQZQXgjs",null,["ClmqQZQXgjs",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680125669985231",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"ClmqQZQXgjs",null,false,null,"1680125669985231",null,"1680125669985231",true,1680125669985,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680125669985231",true,0,null,false],[["sklE9n0I824",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680126062610655","0",null,[[null,"sklE9n0I824",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],"oh yeah",null,null,null,[["oh yeah",null,[]]],null,"1680126062610655",null,null,false,false,1680126062610,["sklE9n0I824",null,["sklE9n0I824",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680126062610655",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1]]],null,0,null,"sklE9n0I824",null,false,null,"1680126062610655",null,"1680126062610655",false,1680126062610,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680126062610655",true,0,null,false],[["Q7eKkeX0yN8",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680126081539967","0",null,[[null,"Q7eKkeX0yN8",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"?",null,null,null,[["?",null,[]]],null,"1680126081539967",null,null,false,false,1680126081539,["Q7eKkeX0yN8",null,["Q7eKkeX0yN8",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680126081539967",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"Q7eKkeX0yN8",null,false,null,"1680126081539967",null,"1680126081539967",false,1680126081539,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680126081539967",true,0,null,false],[["gMirOIknqsA",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680727996948431","0",null,[[null,"gMirOIknqsA",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"testing",null,null,null,[["testing",null,[]]],null,"1680727996948431",null,null,false,false,1680727996948,["gMirOIknqsA",null,["gMirOIknqsA",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680727996948431",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"gMirOIknqsA",null,false,null,"1680727996948431",null,"1680727996948431",true,1680727996948,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680727996948431",true,0,null,false],[["IQmqJd7MiHs",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680728781692591","0",null,[[null,"IQmqJd7MiHs",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],"hey whats up?",null,null,null,[["hey whats up?",null,[]]],null,"1680728781692591",null,null,false,false,1680728781692,["IQmqJd7MiHs",null,["IQmqJd7MiHs",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680728781692591",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1]]],null,0,null,"IQmqJd7MiHs",null,false,null,"1680728781692591",null,"1680728781692591",false,1680728781692,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680728781692591",true,0,null,false],[["c42Rat4k5Jw",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680728789998495","0",null,[[null,"c42Rat4k5Jw",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"not much just chilling",null,null,null,[["not much just chilling",null,[]]],null,"1680728789998495",null,null,false,false,1680728789998,["c42Rat4k5Jw",null,["c42Rat4k5Jw",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680728789998495",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"c42Rat4k5Jw",null,false,null,"1680728789998495",null,"1680728789998495",false,1680728789998,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680728789998495",true,0,null,false],[["DelBu_NIMEs",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680728794872911","0",null,[[null,"DelBu_NIMEs",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],"cool me too!",null,null,null,[["cool me too!",null,[]]],null,"1680728794872911",null,null,false,false,1680728794872,["DelBu_NIMEs",null,["DelBu_NIMEs",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680728794872911",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1]]],null,0,null,"DelBu_NIMEs",null,false,null,"1680728794872911",null,"1680728794872911",false,1680728794872,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680728794872911",true,0,null,false],[["sYC0hGwKQXg",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680729955006783","0",null,[[null,"sYC0hGwKQXg",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],"weee!",null,null,null,[["weee!",null,[]]],null,"1680729955006783",null,null,false,false,1680729955006,["sYC0hGwKQXg",null,["sYC0hGwKQXg",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680729955006783",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1]]],null,0,null,"sYC0hGwKQXg",null,false,null,"1680729955006783",null,"1680729955006783",false,1680729955006,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680729955006783",true,0,null,false],[["cJENqwLDjYU",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680731097890543","0",null,[[null,"cJENqwLDjYU",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],"test",null,null,null,[["test",null,[]]],null,"1680731097890543",null,null,false,false,1680731097890,["cJENqwLDjYU",null,["cJENqwLDjYU",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680731097890543",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1]]],null,0,null,"cJENqwLDjYU",null,false,null,"1680731097890543",null,"1680731097890543",false,1680731097890,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680731097890543",true,0,null,false],[["-6CumLiwpa4",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680731107541999","0",null,[[null,"-6CumLiwpa4",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],"and again",null,null,null,[["and again",null,[]]],null,"1680731107541999",null,null,false,false,1680731107541,["-6CumLiwpa4",null,["-6CumLiwpa4",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680731107541999",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1]]],null,0,null,"-6CumLiwpa4",null,false,null,"1680731107541999",null,"1680731107541999",false,1680731107541,null,null,null,false,null,null,false,false,null,0,null,true,null,true,null,null,"1680731107541999",true,0,null,false],[["HLx9yWj2Lpg",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680731117605839","0",null,[[null,"HLx9yWj2Lpg",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],"hmm",null,null,null,[["hmm",null,[]]],null,"1680731117605839",null,null,false,false,1680731117605,["HLx9yWj2Lpg",null,["HLx9yWj2Lpg",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680731117605839",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1]]],null,0,null,"HLx9yWj2Lpg",null,false,null,"1680731117605839",null,"1680731117605839",false,1680731117605,null,null,null,false,null,null,false,false,null,0,null,true,null,true,null,null,"1680731117605839",true,0,null,false],[["Wac_nScpeYE",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680731142507055","0",null,[[null,"Wac_nScpeYE",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],"hmm",null,null,null,[["hmm",null,[]]],null,"1680731142507055",null,null,false,false,1680731142507,["Wac_nScpeYE",null,["Wac_nScpeYE",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680731142507055",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1]]],null,0,null,"Wac_nScpeYE",null,false,null,"1680731142507055",null,"1680731142507055",false,1680731142507,null,null,null,false,null,null,false,false,null,0,null,true,null,true,null,null,"1680731142507055",true,0,null,false],[["FQSK122qK8k",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680766230312831","0",null,[[null,"FQSK122qK8k",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"beep",null,null,null,[["beep",null,[]]],null,"1680766230312831",null,null,false,false,1680766230312,["FQSK122qK8k",null,["FQSK122qK8k",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680766230312831",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"FQSK122qK8k",null,false,null,"1680766230312831",null,"1680766230312831",true,1680766230312,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680766230312831",true,0,null,false],[["tgWi0Tg9kZk",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680766289793887","0",null,[[null,"tgWi0Tg9kZk",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"oh shit",null,null,null,[["oh shit",null,[]]],null,"1680766289793887",null,null,false,false,1680766289793,["tgWi0Tg9kZk",null,["tgWi0Tg9kZk",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680766289793887",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"tgWi0Tg9kZk",null,false,null,"1680766289793887",null,"1680766289793887",false,1680766289793,null,null,null,false,null,null,false,false,null,0,null,true,null,true,null,null,"1680766289793887",true,0,null,false],[["op4e7aQ0joY",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680766352119279","0",null,[[null,"op4e7aQ0joY",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"uhhh",null,null,null,[["uhhh",null,[]]],null,"1680766352119279",null,null,false,false,1680766352119,["op4e7aQ0joY",null,["op4e7aQ0joY",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680766352119279",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"op4e7aQ0joY",null,false,null,"1680766352119279",null,"1680766352119279",false,1680766352119,null,null,null,false,null,null,false,false,null,0,null,true,null,true,null,null,"1680766352119279",true,0,null,false],[["ZOjgkAch6sA",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680766438244607","0",null,[[null,"ZOjgkAch6sA",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"hmmmpf",null,null,null,[["hmmmpf",null,[]]],null,"1680766438244607",null,null,false,false,1680766438244,["ZOjgkAch6sA",null,["ZOjgkAch6sA",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680766438244607",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"ZOjgkAch6sA",null,false,null,"1680766438244607",null,"1680766438244607",false,1680766438244,null,null,null,false,null,null,false,false,null,0,null,true,null,true,null,null,"1680766438244607",true,0,null,false],[["pesXALIS9RQ",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680766633839727","0",null,[[null,"pesXALIS9RQ",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"bleep",null,null,null,[["bleep",null,[]]],null,"1680766633839727",null,null,false,false,1680766633839,["pesXALIS9RQ",null,["pesXALIS9RQ",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680766633839727",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"pesXALIS9RQ",null,false,null,"1680766633839727",null,"1680766633839727",false,1680766633839,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680766633839727",true,0,null,false],[["eY57eAehwW8",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680769045369455","0",null,[[null,"eY57eAehwW8",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"weeee",null,null,null,[["weeee",null,[]]],null,"1680769045369455",null,null,false,false,1680769045369,["eY57eAehwW8",null,["eY57eAehwW8",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680769045369455",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"eY57eAehwW8",null,false,null,"1680769045369455",null,"1680769045369455",false,1680769045369,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680769045369455",true,0,null,false],[["KoP-ZmO9CXw",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680807987724479","0",null,[[null,"KoP-ZmO9CXw",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"bleepity bloopity",null,null,null,[["bleepity bloopity",null,[]]],null,"1680807987724479",null,null,false,false,1680807987724,["KoP-ZmO9CXw",null,["KoP-ZmO9CXw",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680807987724479",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],null,0,null,"KoP-ZmO9CXw",null,false,null,"1680807987724479",null,"1680807987724479",false,1680807987724,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,null,"1680807987724479",true,0,null,false],[["tc43GFv6nBg",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680811523142751","0",null,[[null,"tc43GFv6nBg",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],"bleepo",null,null,null,[["bleepo",null,[]]],null,"1680811523142751",null,null,false,false,1680811523142,["tc43GFv6nBg",null,["tc43GFv6nBg",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680811523142751",null,null,null,null,null,null,null,false,null,false,null,3,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1]]],null,0,null,"tc43GFv6nBg",null,false,null,"1680811523142751",null,"1680811523142751",false,1680811523142,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,[[["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],null,null,null,null,null,null,null,null,1680811523142751]],"1680811523142751",true,0,null,false],[["5Zp7Bd88JQw",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]],"1680812258275247","0",null,[[null,"5Zp7Bd88JQw",["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],"wheeeeeeeee!",null,null,null,[["wheeeeeeeee!",null,[]]],null,"1680812258275247",null,null,true,false,1680812258275,["5Zp7Bd88JQw",null,["5Zp7Bd88JQw",null,["dm/1bM4JkAAAAE","1bM4JkAAAAE",5]]],null,"1680812258275247",null,null,null,null,null,null,null,false,null,false,null,1,null,null,null,null,null,null,1,null,null,null,null,null,null,2,2,null,null,null,null,null,null,null,null,null,null,null,null,null,null,null,["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1]]],true,0,null,"5Zp7Bd88JQw",null,false,null,"1680812258275247",null,"1680812258275247",false,1680812258275,null,null,null,false,null,null,false,false,null,0,null,null,null,true,null,[[["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],null,null,null,null,null,null,null,null,1680812258275247]],"1680812258275247",true,0,null,false]],["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],null,10,false,true,null,["1680812258275247"],["1680812258809231"],[true,[[["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],null,null,null,null,null,null,null,null,1680811523142751],[["105751002961729238331","","","",null,null,null,1,null,["105751002961729238331","human/105751002961729238331",0],null,false,null,null,null,null,null,1],null,null,null,null,null,null,null,null,1680812258275247]]],false,null,1]
```

## eCT9Zc

`/DynamiteWebDataService.DynamiteGetMemberList`

Request:

```
[null,null,[[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],["user/101612323147699054057",null,"101612323147699054057",null,["101612323147699054057","human/101612323147699054057",0],"user/human/101612323147699054057"]]]]
```

Response:

```
[null,[[[null,["user/101612323147699054057",null,"101612323147699054057",null,["101612323147699054057","human/101612323147699054057",0],"user/human/101612323147699054057"]],[["user/101612323147699054057",null,"101612323147699054057",null,["101612323147699054057","human/101612323147699054057",0],"user/human/101612323147699054057"],["101612323147699054057","Mirg repaer","https://lh3.googleusercontent.com/a/AGNmyxZuyR7oIaHZSLkZr8jDCcKPlGSYyg7DKS8gDilF\\u003dk-no-mo","mirgy04@gmail.com",null,true,"Mirg",1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,[[]],null,null,1,1],null,true]]]]
```

## qL7xZc

Request:

```
[[1],27]
```

Response:

```
[[[["😃",[":smile-with-big-eyes:"]],null,1682708780735444]]]
```

## aQdzwb

Request:

```
[null,[44],[]]
```

Response:

```
[[0,false,[0,0,0,0,0,0,null,null,null,null,0,0,0,0,0,0,0,null,0,0,0,0,0,0,0,0,0,0,0,[],[],[]],false,true,false,0,1,"",0,null,0,[],[],false,false,[false,true,true],false,false,[null,null,null,null,null,null,null,null,null,null,null,null,null,[]],true,0,0,2,[],0,true,0,[false]],["1680812258809231"]]
```

## X1NQAf

`/DynamiteWebDataService.DynamiteUpdateGroupLastReadTime`

Request:

```
[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],"1680812258275247"]
```

Response:

```
[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],["1680812742262875","1680812258809231"]]
```

## G9xNb

`/DynamiteWebDataService.DynamiteGetTopicListPageDown`

Request:

```
[["dm/1bM4JkAAAAE","1bM4JkAAAAE",5],"1680812258275247",null,null,null,null,null,1,true,2]
```

Response:

```
[null,10,true,["1680812258275247"],[]]
```

## Ohfn2c

Occurred when creating a space

Request:

```
[]
```

Response:

```
[]
```

## bQZNRe

Happened when creating a space which I named `force`, set the description to
`i dunno`, and invited `gary.kramlich@gmail.com`.

Request:

```
["force",null,null,"L9THZ-vGPHY",null,[1],[[1]],[[[["105751002961729238331","human/105751002961729238331",0],"gary.kramlich@gmail.com"]]],1,[],null,["i dunno"],4,null,null,9,false]
```

Response:

```
[["space/AAAA39xdNlg","AAAA39xdNlg",2],[["space/AAAA39xdNlg","AAAA39xdNlg",2],null,"force",null,null,null,false,null,"1680814404696557","1680814404696557",null,0,false,1680814404696,null,null,null,null,null,null,["101612323147699054057",null,null,"",null,null,null,null,null,["101612323147699054057","human/101612323147699054057",0],null,null,null,null,null,null,null,3],["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],1680814404696,null,null,null,false,"1680814404696557",null,null,[true,2,null,null,null,null,true],null,[1],null,null,true,false,1680814404696,[2],[[]],null,false,null,null,[],null,null,"https://lh3.googleusercontent.com/dra/ANaj5ZoxnrhGIL39xSirM82WcRy1ueaSES5nB96eTPMNz8DtJmHFwz3H21ZWlg","hangouts-chat-b182c7a086fd4605@chat.google.com",null,null,"0",1,null,0,null,null,4,false,null,true,[[true]],["i dunno"],"1680814404696557",2,null,4,[1],null,null,true,["0",false],[20939826,20939832],null,null,null,[],[]],["1680814404696557","0"],[],[[null,null,null,[["user/105751002961729238331",null,"105751002961729238331",null,["105751002961729238331","human/105751002961729238331",0],"user/human/105751002961729238331"],["105751002961729238331",null,null,null,null,null,null,null,null,["105751002961729238331","human/105751002961729238331",0],null,null,null,null,null,null,null,3]],2]]]
```

## W9QdYe

`/DynamiteWebDataService.DynamiteGetGroup`

Happened when creating a space

Request:

```
[["space/AAAA39xdNlg","AAAA39xdNlg",2],null,null,null,null,null,[1680814404,null]]
```

Response:

```
[[["space/AAAA39xdNlg","AAAA39xdNlg",2],null,"force",null,null,null,false,null,"1680814404696557","1680814404696557",null,0,false,1680814404696,null,null,null,null,null,null,["101612323147699054057",null,null,"",null,null,null,null,null,["101612323147699054057","human/101612323147699054057",0],null,null,null,null,null,null,null,3],["101612323147699054057","","","",null,null,null,1,null,["101612323147699054057","human/101612323147699054057",0],null,false,null,null,null,null,null,1],1680814404696,null,null,null,false,"1680814404774815",null,null,[true,2,null,null,null,null,true],null,[1],null,null,true,false,1680814404696,[2],[[]],null,false,null,null,[],null,null,"https://lh3.googleusercontent.com/dra/ANaj5ZoxnrhGIL39xSirM82WcRy1ueaSES5nB96eTPMNz8DtJmHFwz3H21ZWlg","hangouts-chat-b182c7a086fd4605@chat.google.com",null,null,"0",1,null,0,null,null,4,false,null,true,[[true]],["i dunno"],"1680814404696557",2,null,4,[1],null,null,true,["0",false],[20939826,20939832],null,null,null,[[[2,1,2],[0,2,2]]],[]],null,["1680814404774815"],["1680812742386767"]]
```

## lEfKt

Seen during space creation/join

Request:

```
[[[["space/AAAA39xdNlg","AAAA39xdNlg",2],["user/101612323147699054057",null,"101612323147699054057",null,["101612323147699054057","human/101612323147699054057",0],"user/human/101612323147699054057"]]]]
```

Response:

```
[[[[[["space/AAAA39xdNlg","AAAA39xdNlg",2],["user/101612323147699054057",null,"101612323147699054057",null,["101612323147699054057","human/101612323147699054057",0],"user/human/101612323147699054057"]],2,4]]]]
```
