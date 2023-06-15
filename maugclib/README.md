# maugclib
This is a "fork" of [tdryer/hangups](https://github.com/tdryer/hangups) that uses Google Chat instead of Hangouts.
All the extra bloat is removed since the bridge doesn't use it.

## Authentication

To authenticate you need to login to your google account. You should start this
process from https://chat.google.com. This will automatically redirect you to
the login if necessary. Once logged in, open the developer tools in your
browser. From here we need to fill out the following JSON object with the
values of a number of cookies. See the browser specific documentation below on
how to get the value of these cookies from your browser.

```
{
	"/": {
		"COMPASS": "",
		"SSID": "",
		"SID": "",
		"OSID": "",
		"HSID": ""
	},
	"/u/0/webchannel/": {
		"COMPASS": ""
	}
}
```

To actually log in with this, it will need to be converted to a Python
dictionary and then passed into `maugclib.auth.TokenManager.from_cookies`. You
can then pass the `TokenManager` instance into `maugclib.client.Client()` as
normal and everything should kick off.

### Chrome

Click on `Application` in the top of the `DevTools` window. Then find `Storage`
on the left side of the screen. Scroll down to `Cookies` and expand it. Select
`https://chat.google.com`.

From here, you'll have to double click on the value
cell for each cookie to get into an `edit` mode. From here you can copy the
value via keyboard or the right-click context menu.

> Note that you will need to enter the `COMPASS` cookie twice in the JSON
object.

### Firefox

Click on `Storage` at the top of the `Developer Tools` window. Then find
`Cookies` on the left side of the screen and expand it. Select
`https://chat.google.com`.

From here, you'll have to double click on the value
cell for each cookie to get into an `edit` mode. From here you can copy the
value via keyboard or the right-click context menu.

> Note: There are two distinct cookies named `COMPASS`. One of them has a path
of `/` and the other has a path of `/u/0/webchannel/` and they should be
entered in the appropriate section in the JSON object.
