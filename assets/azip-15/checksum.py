import base58

from eth_hash.auto import keccak


def binary_chain_id(evm_chain_id: int, rollup_contract_address: bytes) -> bytes:
    # First 23 bytes (184 bits) of keccak256(abi.encodePacked(uint256, address)):
    # 32-byte big-endian uint || 20-byte address. 23 bytes so the base58btc encoding
    # fits within CAIP-2's 32-char limit.
    preimage = evm_chain_id.to_bytes(32, "big") + rollup_contract_address
    return keccak(preimage)[:23]


def deterministic_chain_id(evm_chain_id: int, rollup_contract_address: bytes) -> str:
    encoded = base58.b58encode(binary_chain_id(evm_chain_id, rollup_contract_address)).decode("ascii")
    # Left-pad with '1' (base58btc's zero) to guarantee a fixed 32-char length.
    return encoded.rjust(32, "1")


def checksum_encode(aztec_address: bytes, evm_chain_id: int, rollup_contract_address: bytes) -> str:
    hex_addr = aztec_address.hex()  # 64 lower-case hex chars
    chain_hash = binary_chain_id(evm_chain_id, rollup_contract_address)[:8]  # first 64 bits

    out = []
    for i, ch in enumerate(hex_addr):
        bit = (chain_hash[i >> 3] >> (7 - (i & 7))) & 1
        if ch in "abcdef" and bit == 1:
            out.append(ch.upper())
        else:
            out.append(ch)
    return "".join(out)


if __name__ == "__main__":
    aztec_address = bytes.fromhex(
        "9203544e42ba86847ca8458432f7c0265ce567e74064cb25b2a9723c390463c2"
    )
    alpha = (1, bytes.fromhex("Ae2001f7e21d5EcABf6234E9FDd1E76F50F74962"))
    testnet = (11155111, bytes.fromhex("f6D0D42aCE06829bECB78C74F49879528fC632c1"))

    for name, (cid, addr) in [("alpha", alpha), ("testnet", testnet)]:
        print(f"{name}:")
        print(f"  binary id: 0x{binary_chain_id(cid, addr).hex()}")
        print(f"  chain id : {deterministic_chain_id(cid, addr)}")
        print(f"  address  : {checksum_encode(aztec_address, cid, addr)}")
