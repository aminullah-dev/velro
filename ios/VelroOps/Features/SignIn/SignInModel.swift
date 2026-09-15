import Foundation
import Observation
import VelroCore

/// Staff sign-in: the admin panel's SignIn.tsx.
///
/// The same phone and code as the apps -- no second credential system -- but
/// asked for as the console (`audience: "staff"`), so the server only
/// actually sends to a number that already holds a staff role. Email is the
/// default channel: free, and it reaches a laptop in another country when the
/// SIM does not. A development server echoes the code, and it is filled in.
@MainActor
@Observable
final class SignInModel {
    enum Step { case phone, code }

    var step: Step = .phone
    var phone = "" { didSet { error = nil } }
    var code = "" { didSet { if code.count > 8 { code = String(code.prefix(8)) }; error = nil } }
    var channel = API.channelEmail { didSet { error = nil } }
    /// What actually carried the code: an account with no address on file
    /// gets an SMS whatever was asked for.
    private(set) var sentChannel = API.channelSMS
    private(set) var isSubmitting = false
    private(set) var error: APIError?
    /// Seconds before another code may be asked for. An SMS costs money.
    private(set) var resendAfterSeconds = 0

    private let ops: OpsModel
    private var countdown: Task<Void, Never>?

    init(ops: OpsModel) { self.ops = ops }

    private var latinPhone: String { Numerals.latin(phone).trimmingCharacters(in: .whitespacesAndNewlines) }

    var canSubmitPhone: Bool { latinPhone.filter(\.isNumber).count >= 9 && !isSubmitting }
    var canSubmitCode: Bool { code.count >= 4 && !isSubmitting }
    var canResend: Bool { resendAfterSeconds <= 0 && !isSubmitting }

    func requestCode() async {
        guard canSubmitPhone else { return }
        if step == .code && !canResend { return }
        isSubmitting = true
        error = nil
        ops.clearSignOutReason()
        let result = await ops.send(API.requestStaffOtp(phone: latinPhone, locale: ops.locale, channel: channel))
        isSubmitting = false
        switch result {
        case .success(let sent):
            step = .code
            sentChannel = sent.channel ?? API.channelSMS
            resendAfterSeconds = sent.resendAfterSeconds
            // Only a development server sends this; production sends nil.
            code = sent.debugCode ?? ""
            startCountdown()
        case .failure(let failure):
            fail(failure)
        }
    }

    func submitCode() async {
        guard canSubmitCode else { return }
        isSubmitting = true
        error = nil
        let result = await ops.send(
            API.verifyOtp(phone: latinPhone, code: Numerals.latin(code), deviceId: ops.store.deviceId, locale: ops.locale)
        )
        isSubmitting = false
        switch result {
        case .success(let session):
            countdown?.cancel()
            // A passenger's or a driver's code is valid; it simply opens
            // nothing here. The notice says so.
            if !ops.signedIn(session) {
                step = .phone
                code = ""
            }
        case .failure(let failure):
            fail(failure)
        }
    }

    func back() {
        step = .phone
        code = ""
        error = nil
    }

    private func fail(_ failure: APIError) {
        guard failure != .cancelled else { return }
        if failure.code == "OTP_INVALID" { code = "" }
        if failure.code == "OTP_EXPIRED" { step = .phone }
        error = failure
    }

    private func startCountdown() {
        countdown?.cancel()
        countdown = Task { [weak self] in
            while let self, self.resendAfterSeconds > 0 {
                try? await Task.sleep(for: .seconds(1))
                if Task.isCancelled { return }
                self.resendAfterSeconds -= 1
            }
        }
    }
}
