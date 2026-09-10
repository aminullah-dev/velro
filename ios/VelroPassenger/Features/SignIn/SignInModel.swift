import Foundation
import Observation
import VelroCore

/// Sign-in state. The error is kept as a code, never a sentence: the view
/// says it in the language being read, so a language change mid-error is
/// still right.
@MainActor
@Observable
final class SignInModel {
    enum Step { case phone, code }

    var step: Step = .phone
    var phone = "" { didSet { error = nil } }
    var code = "" { didSet { if code.count > 8 { code = String(code.prefix(8)) }; error = nil } }
    /// Where the code should go, chosen by the person: they know whether they
    /// use Telegram and a prefix cannot tell us. It matters -- a Telegram code
    /// costs a cent, an SMS about forty-five, against ~110 messages a month.
    /// SMS is the default because it reaches a phone with no data at all.
    var channel = API.channelSMS { didSet { error = nil } }
    /// Where it actually went. A Telegram code that could not be delivered
    /// comes back as SMS, and the next step must point at the right app.
    private(set) var sentChannel = API.channelSMS
    private(set) var isSubmitting = false
    private(set) var error: APIError?
    /// Seconds before another code may be asked for. The server enforces its
    /// own limit; this is the cost control. Three impatient taps are three
    /// real SMS, and the third earns a rate-limit error nobody can interpret.
    private(set) var resendAfterSeconds = 0

    private let app: AppModel
    private var countdown: Task<Void, Never>?

    init(app: AppModel) { self.app = app }

    var canSubmitPhone: Bool { phone.filter(\.isNumber).count >= 9 && !isSubmitting }
    var canSubmitCode: Bool { code.count >= 4 && !isSubmitting }
    var canResend: Bool { resendAfterSeconds <= 0 && !isSubmitting }

    func requestCode() async {
        guard canSubmitPhone else { return }
        // The resend button is disabled while the clock runs, but the guard is
        // here too: a disabled button is a drawing, and this spends money.
        if step == .code && !canResend { return }

        isSubmitting = true
        error = nil
        let result = await app.client.send(API.requestOtp(phone: phone, locale: app.locale, channel: channel))
        isSubmitting = false
        switch result {
        case .success(let sent):
            step = .code
            sentChannel = sent.channel ?? API.channelSMS
            resendAfterSeconds = sent.resendAfterSeconds
            // Only a development server echoes the code; production sends nil
            // and the field starts empty.
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
        let result = await app.client.send(
            API.verifyOtp(phone: phone, code: code, deviceId: app.store.deviceId, locale: app.locale)
        )
        isSubmitting = false
        switch result {
        case .success(let session):
            countdown?.cancel()
            app.signedIn(session)
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
        // A wrong code clears the field; an expired one goes back to ask for a
        // new code rather than leaving somebody retyping into a dead one.
        if failure.code == "OTP_INVALID" { code = "" }
        if failure.code == "OTP_EXPIRED" { step = .phone }
        // `code` and `step` observers clear the error; put it back.
        error = failure
    }

    /// Owned here, not by the view, so it keeps counting when the screen is
    /// rebuilt -- a clock that restarts hands the button back early.
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
