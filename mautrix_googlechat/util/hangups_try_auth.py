# mautrix-googlechat - A Matrix-Google Chat puppeting bridge
# Copyright (C) 2021 Tulir Asokan
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
from typing import NamedTuple, Optional

from hangups.auth import TokenManager, RefreshTokenCache, GoogleAuthError

TryAuthResp = NamedTuple('TryAuthResp', success=bool, token_manager=Optional[TokenManager],
                         error=Optional[GoogleAuthError])


async def try_auth(refresh_token_cache: RefreshTokenCache) -> TryAuthResp:
    try:
        token_mgr = await TokenManager.from_refresh_token(refresh_token_cache)
        return TryAuthResp(success=True, token_manager=token_mgr, error=None)
    except GoogleAuthError as e:
        return TryAuthResp(success=False, token_manager=None, error=e)
