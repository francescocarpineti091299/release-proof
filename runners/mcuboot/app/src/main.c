/* SPDX-License-Identifier: MIT
 *
 * ReleaseProof demo application for MCUboot.
 *
 * Prints one deterministic UART marker derived from the MCUboot image header and TLV area of the
 * image it is executing from (the code partition), so the reported version and signer always
 * reflect the image actually booted:
 *
 *   RP-APP version=<major>.<minor>.<revision> build=<n> key=<sha256(pubkey)[0:8] hex> slot=0x<addr>
 */
#include <zephyr/kernel.h>
#include <zephyr/devicetree.h>
#include <zephyr/sys/printk.h>
#include <stdint.h>
#include <string.h>

#define RP_FLASH_BASE   DT_REG_ADDR(DT_CHOSEN(zephyr_flash))
#define RP_CODE_PART    DT_CHOSEN(zephyr_code_partition)
#define RP_SLOT_ADDR    (RP_FLASH_BASE + DT_REG_ADDR(RP_CODE_PART))

#define IMAGE_MAGIC            0x96f3b83dU
#define IMAGE_TLV_INFO_MAGIC   0x6907U
#define IMAGE_TLV_PROT_MAGIC   0x6908U
#define IMAGE_TLV_KEYHASH      0x01U

struct rp_image_header {
	uint32_t magic;
	uint32_t load_addr;
	uint16_t hdr_size;
	uint16_t protect_tlv_size;
	uint32_t img_size;
	uint32_t flags;
	uint8_t major;
	uint8_t minor;
	uint16_t revision;
	uint32_t build_num;
	uint32_t pad1;
} __packed;

static uint16_t rd16(uintptr_t a)
{
	uint16_t v;

	memcpy(&v, (const void *)a, sizeof(v));
	return v;
}

int main(void)
{
	struct rp_image_header hdr;
	char key[17] = "none";

	memcpy(&hdr, (const void *)RP_SLOT_ADDR, sizeof(hdr));
	if (hdr.magic != IMAGE_MAGIC) {
		printk("RP-APP version=unknown key=none slot=0x%lx\n", (unsigned long)RP_SLOT_ADDR);
		return 0;
	}

	uintptr_t off = RP_SLOT_ADDR + hdr.hdr_size + hdr.img_size;

	if (rd16(off) == IMAGE_TLV_PROT_MAGIC) {
		off += hdr.protect_tlv_size;
	}
	if (rd16(off) == IMAGE_TLV_INFO_MAGIC) {
		uintptr_t end = off + rd16(off + 2);

		for (uintptr_t p = off + 4; p + 4 <= end;) {
			uint16_t type = rd16(p);
			uint16_t len = rd16(p + 2);

			if (type == IMAGE_TLV_KEYHASH && len >= 8) {
				const uint8_t *h = (const uint8_t *)(p + 4);

				for (int i = 0; i < 8; i++) {
					static const char hex[] = "0123456789abcdef";

					key[2 * i] = hex[h[i] >> 4];
					key[2 * i + 1] = hex[h[i] & 0xf];
				}
				key[16] = '\0';
				break;
			}
			p += 4 + len;
		}
	}

	printk("RP-APP version=%u.%u.%u build=%u key=%s slot=0x%lx\n", hdr.major, hdr.minor,
	       hdr.revision, hdr.build_num, key, (unsigned long)RP_SLOT_ADDR);

	while (1) {
		k_sleep(K_SECONDS(1));
	}
	return 0;
}
