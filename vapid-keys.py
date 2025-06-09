from pywebpush import generate_vapid_keys

vapid_keys = generate_vapid_keys()
print("Public Key:", vapid_keys["publicKey"])
print("Private Key:", vapid_keys["privateKey"])


# {
# "subject": "mailto: <>@me.com>",
# "publicKey": "<>",
# "privateKey": "<>"
# }
