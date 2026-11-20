export async function api(path, data) {
  const response = await fetch("/api/" + path, data === undefined ? {} : {
    method: "POST", headers: {"Content-Type": "application/json", "X-Chores-Request": "1"}, body: JSON.stringify(data)
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Something went wrong.");
  return payload;
}
