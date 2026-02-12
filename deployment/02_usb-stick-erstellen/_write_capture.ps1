# Fallback: custom-ocs-capture inline erstellen
# Wird nur verwendet wenn custom-ocs/custom-ocs-capture nicht existiert
param([string]$OutputPath)

$script = @'
#!/bin/bash
echo '============================================'
echo '  FexoBooth - IMAGE ERSTELLEN'
echo '============================================'
echo ''

if [ -b /dev/mmcblk0 ]; then
    TARGET_DISK=mmcblk0
    echo "Erkannt: eMMC (/dev/mmcblk0)"
elif [ -b /dev/nvme0n1 ]; then
    TARGET_DISK=nvme0n1
    echo "Erkannt: NVMe (/dev/nvme0n1)"
elif [ -b /dev/sda ]; then
    USB_DEV=$(mount | grep /home/partimag | awk '{print $1}' | sed 's/[0-9]*$//')
    if [ "/dev/sda" != "$USB_DEV" ]; then
        TARGET_DISK=sda
        echo "Erkannt: /dev/sda"
    elif [ -b /dev/sdb ]; then
        TARGET_DISK=sdb
        echo "Erkannt: /dev/sdb"
    fi
fi

if [ -z "$TARGET_DISK" ]; then
    echo "FEHLER: Keine Festplatte gefunden!"
    lsblk -d -o NAME,SIZE,TYPE,MODEL
    read -p "Enter zum Neustarten..." dummy
    reboot
fi

IMAGE_NAME=fexobooth-image-$(date +%Y%m%d)
echo "Disk: /dev/$TARGET_DISK  Image: $IMAGE_NAME"
echo ""
/usr/sbin/ocs-sr -q2 -c -j2 -z5 -i 4096 -sfsck -senc -p reboot savedisk "$IMAGE_NAME" "$TARGET_DISK"
'@

$utf8 = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText($OutputPath, $script.Replace("`r`n","`n"), $utf8)
