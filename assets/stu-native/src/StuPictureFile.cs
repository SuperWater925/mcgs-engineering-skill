using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using System.Xml;

namespace McgsInternalBridge {
    public static partial class EngineEntry {
        private const int StuPictureImportLimit = 16 * 1024 * 1024;
        private const int StuPictureBmp = 0, StuPictureJpeg = 1, StuPicturePng = 2, StuPictureSvg = 3;


        private sealed class StuPictureFile {
            internal int Kind, Width, Height;
            internal byte[] Bytes, NativeBytes;
            internal bool Normalized;
        }

        private static string StuPictureFormatName(int kind) {
            switch (kind) {
                case StuPictureBmp: return "bmp";
                case StuPictureJpeg: return "jpeg";
                case StuPicturePng: return "png";
                case StuPictureSvg: return "svg";
                default: return "unknown";
            }
        }

        private static int StuPictureKindFromPath(string path) {
            Require(Path.IsPathRooted(path), "请指定图片文件的绝对路径");
            switch (Path.GetExtension(path).ToLowerInvariant()) {
                case ".bmp": return StuPictureBmp;
                case ".jpg": case ".jpeg": return StuPictureJpeg;
                case ".png": return StuPicturePng;
                case ".svg": return StuPictureSvg;
                default: throw new InvalidOperationException("当前文件格式须为 BMP、JPEG、PNG 或 SVG");
            }
        }

        private static StuPictureFile StuPictureReadFile(string path, string sha256) {
            int kind = StuPictureKindFromPath(path);
            byte[] bytes;
            using (var stream = File.Open(path, FileMode.Open, FileAccess.Read, FileShare.Read)) {
                Require(stream.Length >= 14 && stream.Length <= StuPictureImportLimit - 1024,
                    "图片文件大小超出原厂归档范围");
                using (var reader = new BinaryReader(stream)) bytes = reader.ReadBytes((int)stream.Length);
            }
            Require(String.Equals(StuPictureHex(bytes), sha256, StringComparison.OrdinalIgnoreCase),
                "图片文件摘要不一致");
            int width, height;
            bool normalized = false;
            if (kind == StuPictureSvg) {
                StuPictureSvgSize(bytes, out width, out height);
            } else {
                StuPictureRasterSize(kind, bytes, out width, out height);
                if (kind == StuPictureBmp && BitConverter.ToInt32(bytes, 34) == 0) {
                    Buffer.BlockCopy(BitConverter.GetBytes(bytes.Length - 54), 0, bytes, 34, 4);
                    normalized = true;
                }
            }
            return new StuPictureFile { Kind = kind, Width = width, Height = height, Bytes = bytes,
                NativeBytes = kind == StuPictureSvg ? StuPictureWrapSvg(bytes) : bytes, Normalized = normalized };
        }

        private static void StuPictureCheckDimensions(int width, int height) {
            Require(width > 0 && width <= 8192 && height > 0 && height <= 8192 && (long)width * height <= 16777216,
                "图片分辨率超出已核对范围");
        }

        private static void StuPictureRasterSize(int kind, byte[] bytes, out int width, out int height) {
            if (kind == StuPicturePng) {
                byte[] magic = {137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82};
                Require(bytes.Length >= 45 && bytes.Take(magic.Length).SequenceEqual(magic), "PNG 文件头无效");
                width = checked((int)StuPictureBigEndian(bytes, 16));
                height = checked((int)StuPictureBigEndian(bytes, 20));
            } else if (kind == StuPictureJpeg) {
                StuPictureJpegSize(bytes, out width, out height);
            } else {
                Require(kind == StuPictureBmp && bytes.Length >= 54 && bytes[0] == 'B' && bytes[1] == 'M' &&
                    BitConverter.ToInt32(bytes, 2) == bytes.Length && BitConverter.ToInt32(bytes, 6) == 0 &&
                    BitConverter.ToInt32(bytes, 10) == 54 && BitConverter.ToInt32(bytes, 14) == 40 &&
                    BitConverter.ToInt16(bytes, 26) == 1 && BitConverter.ToInt16(bytes, 28) == 24 &&
                    BitConverter.ToInt32(bytes, 30) == 0 && BitConverter.ToInt32(bytes, 46) == 0,
                    "BMP 当前支持标准 24 位无压缩 BITMAPINFOHEADER");
                width = BitConverter.ToInt32(bytes, 18);
                height = BitConverter.ToInt32(bytes, 22);
                StuPictureCheckDimensions(width, height);
                int rasterLength = ((width * 3 + 3) & ~3) * height;
                int storedLength = BitConverter.ToInt32(bytes, 34);
                Require(bytes.Length == 54 + rasterLength && (storedLength == 0 || storedLength == rasterLength),
                    "BMP 像素区长度与分辨率不一致");
            }
            StuPictureCheckDimensions(width, height);
        }

        private static void StuPictureJpegSize(byte[] bytes, out int width, out int height) {
            Require(bytes.Length >= 14 && bytes[0] == 255 && bytes[1] == 216 && bytes[2] == 255 &&
                bytes[bytes.Length - 2] == 255 && bytes[bytes.Length - 1] == 217, "JPEG 文件标记无效");
            width = height = 0;
            int offset = 2;
            while (offset < bytes.Length - 4) {
                Require(bytes[offset++] == 255, "JPEG 区段起点无效");
                while (offset < bytes.Length - 3 && bytes[offset] == 255) offset++;
                int marker = bytes[offset++];
                int length = (bytes[offset] << 8) | bytes[offset + 1];
                Require(length >= 2 && length <= bytes.Length - offset, "JPEG 区段长度无效");
                if (marker == 192 || marker == 193 || marker == 194) {
                    Require(width == 0 && length >= 8 && bytes[offset + 2] == 8, "JPEG 帧类型无效");
                    height = (bytes[offset + 3] << 8) | bytes[offset + 4];
                    width = (bytes[offset + 5] << 8) | bytes[offset + 6];
                }
                if (marker == 218) break;
                offset += length;
            }
            Require(width > 0 && height > 0, "JPEG 缺少受支持的图像帧");
        }

        private static int StuPictureSvgAxis(string text) {
            int pixels;
            if (text == null) return 0;
            if (text.EndsWith("px", StringComparison.Ordinal)) text = text.Substring(0, text.Length - 2);
            return Int32.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out pixels) ? pixels : 0;
        }

        private static void StuPictureSvgSize(byte[] bytes, out int width, out int height) {
            var settings = new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit, XmlResolver = null,
                MaxCharactersInDocument = StuPictureImportLimit };
            using (var input = XmlReader.Create(new MemoryStream(bytes, false), settings)) {
                while (input.Read() && input.NodeType != XmlNodeType.Element)
                    Require(input.NodeType != XmlNodeType.ProcessingInstruction, "SVG 含外部处理指令");
                Require(input.NodeType == XmlNodeType.Element && input.LocalName == "svg" &&
                    input.NamespaceURI == "http://www.w3.org/2000/svg", "SVG 缺少标准根元素");
                width = StuPictureSvgAxis(input.GetAttribute("width"));
                height = StuPictureSvgAxis(input.GetAttribute("height"));
                string viewBox = input.GetAttribute("viewBox");
                if (viewBox != null) {
                    string[] axes = viewBox.Split(new[] { ' ', '\r', '\n', '\t', ',' }, StringSplitOptions.RemoveEmptyEntries);
                    Require(axes.Length == 4, "SVG viewBox 需要四个数值");
                    width = StuPictureSvgAxis(axes[2]);
                    height = StuPictureSvgAxis(axes[3]);
                }
                StuPictureCheckDimensions(width, height);
                do {
                    Require(input.NodeType != XmlNodeType.ProcessingInstruction, "SVG 含外部处理指令");
                    if (input.NodeType == XmlNodeType.Element) {
                        Require(input.LocalName != "script" && input.LocalName != "foreignObject" && input.LocalName != "set" &&
                            !input.LocalName.StartsWith("animate", StringComparison.Ordinal), "SVG contains dynamic content.");
                        if (!input.HasAttributes) continue;
                        while (input.MoveToNextAttribute()) {
                            Require(!input.LocalName.StartsWith("on", StringComparison.OrdinalIgnoreCase) &&
                                (input.LocalName != "href" && input.LocalName != "src" || input.Value.StartsWith("#", StringComparison.Ordinal)),
                                "SVG 图片或链接须使用文件内部引用");
                            StuCheckPictureSvgCss(input.Value);
                        }
                        input.MoveToElement();
                    } else if (input.NodeType == XmlNodeType.Text || input.NodeType == XmlNodeType.CDATA) {
                        StuCheckPictureSvgCss(input.Value);
                    }
                } while (input.Read());
            }
        }

        private static void StuCheckPictureSvgCss(string value) {
            Require(value.IndexOf('\\') < 0 && value.IndexOf("/*", StringComparison.Ordinal) < 0 &&
                value.IndexOf("@import", StringComparison.OrdinalIgnoreCase) < 0 &&
                !Regex.IsMatch(value, @"url\s*\(\s*['""]?(?!['""]|#|\s)", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant),
                "SVG 样式中的图片须使用文件内部引用");
        }

        private static byte[] StuPictureWrapSvg(byte[] raw) {
            // COwnerBitmap's own SVG handler removes this 14-byte file header before passing bytes to Qt.
            var wrapped = new byte[checked(raw.Length + 14)];
            wrapped[0] = (byte)'V';
            wrapped[1] = (byte)'S';
            Buffer.BlockCopy(BitConverter.GetBytes(wrapped.Length), 0, wrapped, 2, 4);
            Buffer.BlockCopy(raw, 0, wrapped, 14, raw.Length);
            return wrapped;
        }

        private static byte[] StuPictureExternalBytes(int kind, byte[] native) {
            if (kind != StuPictureSvg) return native;
            Require(native.Length >= 28 && native[0] == 'V' && native[1] == 'S' &&
                native.Length == BitConverter.ToInt32(native, 2), "原厂 SVG 文件头无效");
            var raw = new byte[native.Length - 14];
            Buffer.BlockCopy(native, 14, raw, 0, raw.Length);
            return raw;
        }

        private static uint StuPictureBigEndian(byte[] bytes, int offset) {
            return ((uint)bytes[offset] << 24) | ((uint)bytes[offset + 1] << 16) |
                ((uint)bytes[offset + 2] << 8) | bytes[offset + 3];
        }

        private static string StuPictureHex(byte[] bytes) {
            using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        }
    }
}