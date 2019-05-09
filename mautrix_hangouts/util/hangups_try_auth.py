# mautrix-hangouts - A Matrix-Hangouts puppeting bridge
# Copyright (C) 2019 Tulir Asokan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from typing import Dict, NamedTuple, Optional

from hangups.auth import (requests, _auth_with_refresh_token, _get_session_cookies, USER_AGENT,
                          GoogleAuthError)

TryAuthResp = NamedTuple('TryAuthResp', success=bool, cookies=Optional[Dict],
                         error=Optional[GoogleAuthError])


def try_auth(refresh_token: str) -> TryAuthResp:
    with requests.Session() as session:
        session.headers = {'user-agent': USER_AGENT}
        try:
            access_token = _auth_with_refresh_token(session, refresh_token)
            return TryAuthResp(success=True, cookies=_get_session_cookies(session, access_token),
                               error=None)
        except GoogleAuthError as e:
            return TryAuthResp(success=False, cookies=None, error=e)
