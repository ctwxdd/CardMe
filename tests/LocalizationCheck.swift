import Foundation

@main
struct LocalizationCheck {
    @MainActor static func main() {
        let chinese = Bundle.main.preferredLocalizations.first == "zh-Hant"
        assert(Bundle.main.localizations.contains("en") && Bundle.main.localizations.contains("zh-Hant"))
        let session = RescueSession()
        assert(session.guidanceTitle == (chinese ? "選擇記憶卡" : "Choose your memory card"))
        assert(L("Rescue to…") == (chinese ? "救回照片並儲存至⋯" : "Rescue to…"))
        assert(L("Search deeper…") == (chinese ? "深入救援⋯" : "Search deeper…"))
        assert(L("Unknown") == (chinese ? "無法確認" : "Unknown"))
        assert(L("Version %@", "0.3.37") == (chinese ? "版本 0.3.37" : "Version 0.3.37"))
        session.receive(Data("SCANNING\t{\"checked\":12}\n".utf8))
        assert(session.status == (chinese ? "正在檢查照片⋯已檢查 12 張" : "Checking photos… 12 checked"))
        session.receive(Data("CARVING\t{\"done\":50,\"total\":100,\"found\":3}\n".utf8))
        assert(session.status == (chinese ? "正在尋找照片⋯已搜尋 50%・找到 3 張" : "Looking for your photos… 50% checked · 3 found"))
        session.receive(Data("FRAGMENTS\t{\"done\":1,\"total\":4,\"found\":2}\n".utf8))
        assert(session.status == (chinese ? "正在重建照片⋯已檢查 25%・重建 2 張" : "Putting photo pieces together… 25% checked · 2 rebuilt"))
        session.receive(Data("IMAGING\t{\"done\":50,\"total\":100}\n".utf8))
        assert(session.status == (chinese ? "正在備份記憶卡⋯已完成 50%" : "Keeping your card safe… 50% copied"))
        session.receive(Data("FILE\t{\"path\":\"IMG_1234.JPG\",\"offset\":512,\"quality\":\"manual_review\",\"reconstruction\":\"mpf_preview_guided\",\"output\":\"/tmp/not-written.JPG\"}\n".utf8))
        assert(session.damaged.last?.name == "IMG_1234.JPG")
        assert(session.damaged.last?.id == "recovered-512")
        assert(session.damaged.last?.detail == (chinese ? "可能是原尺寸照片・請確認內容" : "Full-size candidate · please check"))
        assert(session.damaged.last?.fullSizeRecovered == false)
        let outcome = RecoveryOutcome(photos: [], wholeCardSearch: true)
        assert(outcome.text.contains(chinese ? "未能救回：無法確認" : "Not recovered: unknown"))
        assert(Bundle.main.localizedString(forKey: "NSRemovableVolumesUsageDescription", value: nil, table: "InfoPlist").contains(chinese ? "救回的照片" : "Recovery results"))
        assert(L("new unmapped diagnostic") == "new unmapped diagnostic")
        print("\(Bundle.main.preferredLocalizations): labels, placeholders, photo identity, recovery status and permission copy passed.")
    }
}
