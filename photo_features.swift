import Foundation
import ImageIO
import Vision

guard CommandLine.arguments.count == 3 else {
    fatalError("Usage: photo-features manifest.tsv features.bin")
}
let manifest = try String(contentsOfFile: CommandLine.arguments[1], encoding: .utf8)
let paths = manifest.split(separator: "\n").map(String.init)
let destination = URL(fileURLWithPath: CommandLine.arguments[2])
let thumbnailOptions: [CFString: Any] = [
    kCGImageSourceCreateThumbnailFromImageAlways: true,
    kCGImageSourceCreateThumbnailWithTransform: true,
    kCGImageSourceThumbnailMaxPixelSize: 512,
]
var features = Data()
for (index, path) in paths.enumerated() {
    try autoreleasepool {
        let url = URL(fileURLWithPath: path)
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
              let image = CGImageSourceCreateThumbnailAtIndex(source, 0, thumbnailOptions as CFDictionary) else {
            throw CocoaError(.fileReadCorruptFile, userInfo: [NSFilePathErrorKey: path])
        }
        let request = VNGenerateImageFeaturePrintRequest()
        request.revision = VNGenerateImageFeaturePrintRequestRevision2
        try VNImageRequestHandler(cgImage: image).perform([request])
        guard let result = request.results?.first, result.elementType == .float,
              result.data.count == result.elementCount * MemoryLayout<Float>.size else {
            throw CocoaError(.featureUnsupported, userInfo: [NSFilePathErrorKey: path])
        }
        features.append(result.data)
    }
    if (index + 1) % 500 == 0 {
        FileHandle.standardError.write(Data("\(index + 1)/\(paths.count) photos\n".utf8))
    }
}
try features.write(to: destination, options: .atomic)
