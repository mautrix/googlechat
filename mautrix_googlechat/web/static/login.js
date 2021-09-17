const AUTH_TOKEN = window.location.hash.substr(1)

const views = {}
for (const view of document.querySelectorAll(".view")) {
	const viewName = view.id
		.substr("view-".length)
		.replace(/-([a-z])/g, g => g[1].toUpperCase())
	views[viewName] = view
}

function setView(view) {
	document.querySelector(".view:not(.hidden)").classList.add("hidden")
	view.classList.remove("hidden")
}

async function main() {
	const resp = await fetch("api/verify", {
		method: "POST",
		headers: {
			Authorization: `Bearer ${AUTH_TOKEN}`,
		},
	})
	const data = await resp.json()
	if (resp.status === 401) {
		if (data.errcode === "M_EXPIRED_TOKEN") {
			setView(views.tokenExpired)
		} else {
			setView(views.tokenInvalid)
		}
	} else {
		document.getElementById("start-mxid").value = data.user_id
		views.start.querySelector("form").onsubmit = evt => {
			evt.preventDefault()
			startLogin().catch(console.error)
		}
		setView(views.start)
	}
}

async function startLogin() {
	const resp = await fetch(`api/start`, {
		method: "POST",
		headers: {
			Authorization: `Bearer ${AUTH_TOKEN}`,
		},
	})
	await handleResponse(resp)
}

async function submitStep(stepName) {
	document.getElementById(stepName).disabled = true
	const resp = await fetch(`api/${stepName}`, {
		method: "POST",
		headers: {
			"Authorization": `Bearer ${AUTH_TOKEN}`,
			"Content-Type": "application/json",
		},
		body: JSON.stringify({
			[stepName]: document.getElementById(stepName).value,
		}),
	})
	await handleResponse(resp)
}

async function handleError(resp) {
	console.error("Error response:", resp)
	const data = await resp.json()
	if (data.errcode === "M_EXPIRED_TOKEN") {
		setView(views.tokenExpired)
	} else if (data.errcode === "M_UNKNOWN_TOKEN" || data.errcode === "M_MISSING_TOKEN") {
		setView(views.tokenInvalid)
	} else {
		views.unknownError.querySelector("p").textContent = data.error
		setView(views.unknownError)
	}
	console.error("Unexpected response:", resp)
	console.error(await resp.json())
}

async function handleResponse(resp) {
	if (resp.status !== 200) {
		await handleError(resp)
		return
	}
	const data = await resp.json()
	if (data.status === "success") {
		document.getElementById("login-success-name").textContent = data.name
		setView(views.success)
	} else if (data.status === "fail") {
		views.fail.querySelector("p").textContent = data.error
		setView(views.fail)
	} else if (data.status === "cancelled") {
		setView(views.cancelled)
	} else {
		const form = views.login.querySelector("form")
		if (data.next_step === "authorization") {
			document.getElementById("manual-login-link").href = data.manual_auth_url
		}
		form.onsubmit = evt => {
			evt.preventDefault()
			submitStep(data.next_step).catch(console.error)
		}
		form.querySelector("div.container:not(.hidden)")?.classList.add("hidden")
		form.querySelector(`div.${data.next_step}.container`).classList.remove("hidden")
		setView(views.login)
	}
}

main().catch(console.error)
