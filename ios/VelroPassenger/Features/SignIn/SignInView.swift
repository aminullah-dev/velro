import SwiftUI
import VelroCore

/// Sign in: the brand across the top, the form on a card lying over its edge.
struct SignInView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.strings) private var strings
    @Environment(\.openURL) private var openURL
    @State private var model: SignInModel
    @State private var helpOpen = false

    init(app: AppModel) {
        _model = State(initialValue: SignInModel(app: app))
    }

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 0) {
                    BrandHero(
                        title: strings["app.name"],
                        subtitle: strings["app.tagline"],
                        minHeight: geometry.size.height * 0.36,
                        topInset: geometry.safeAreaInsets.top
                    )

                    VelroCard {
                        VStack(alignment: .leading, spacing: Spacing.xl) {
                            // Straight after a deletion, the screen says so: it
                            // is otherwise indistinguishable from being thrown
                            // out by a fault.
                            if app.accountDeleted {
                                Label(strings["account.delete.done"], systemImage: "checkmark.circle.fill")
                                    .velroFont(.label)
                                    .foregroundStyle(Palette.primary)
                                    .accessibilityIdentifier("signin.account_deleted")
                            }
                            // Language first: somebody who cannot read the form
                            // cannot fill it in.
                            languagePicker
                            switch model.step {
                            case .phone: phoneStep
                            case .code: codeStep
                            }
                            if let error = model.error {
                                InlineError(error: error)
                            }
                        }
                    }
                    .padding(.horizontal, Spacing.gutter)
                    .padding(.top, -Spacing.xl - Spacing.lg)

                    // Help from the one screen a signed-out person can reach:
                    // a session that ran out in a valley with no data to renew
                    // it lands here, and the emergency numbers must too. Outside
                    // the card -- a door out, not a step in the form -- and
                    // without the report, which needs a token.
                    SecondaryButton(label: strings["safety.title"]) { helpOpen = true }
                        .padding(.horizontal, Spacing.gutter)
                        .padding(.top, Spacing.lg)
                        .accessibilityIdentifier("signin.help")

                    // What VELRO keeps, readable before handing over a number.
                    TextAction(label: strings["account.privacy"]) { openURL(app.privacyURL) }
                        .padding(.bottom, Spacing.lg)
                        .accessibilityIdentifier("signin.privacy")
                }
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Palette.background)
            .ignoresSafeArea(edges: .top)
        }
        .animation(.snappy, value: model.step)
        .sheet(isPresented: $helpOpen) {
            HelpSheet(app: app, ride: nil, canReport: false)
        }
    }

    private var languagePicker: some View {
        HStack(spacing: Spacing.sm) {
            ForEach([AppLocale.dari, .pashto, .english], id: \.self) { locale in
                ChoiceChip(label: locale.endonym, selected: app.locale == locale) {
                    app.setLocale(locale)
                }
                // The name of each language is in its own script whatever the
                // app is showing; announce it in that language too.
                .environment(\.locale, Locale(identifier: locale.tag))
            }
        }
    }

    private var phoneStep: some View {
        VStack(alignment: .leading, spacing: Spacing.lg) {
            Text(strings["auth.title.sign_in"])
                .velroFont(.title)
                .foregroundStyle(Palette.onSurface)

            VelroField(
                label: strings["auth.field.phone"],
                text: $model.phone,
                placeholder: "0700 123 456",
                keyboard: .phonePad,
                contentType: .telephoneNumber,
                identifier: "signin.phone"
            )

            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(strings["auth.channel.question"])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
                HStack(spacing: Spacing.sm) {
                    ChoiceChip(label: strings["auth.channel.sms"], selected: model.channel == API.channelSMS) {
                        model.channel = API.channelSMS
                    }
                    ChoiceChip(label: strings["auth.channel.telegram"], selected: model.channel == API.channelTelegram) {
                        model.channel = API.channelTelegram
                    }
                }
            }

            PrimaryButton(
                label: strings["auth.action.send_code"],
                enabled: model.canSubmitPhone,
                loading: model.isSubmitting,
                pill: true
            ) {
                Task { await model.requestCode() }
            }
            .accessibilityIdentifier("signin.send")
        }
    }

    private var codeStep: some View {
        VStack(alignment: .leading, spacing: Spacing.lg) {
            // What happened, not what the field is called: the field has its
            // own label, and nothing else says a message actually went out.
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(strings[
                    model.sentChannel == API.channelTelegram ? "auth.hint.code_sent_telegram" : "auth.hint.code_sent"
                ])
                .velroFont(.heading)
                .foregroundStyle(Palette.onSurface)
                Text(model.phone)
                    .velroFont(.body)
                    .foregroundStyle(Palette.onSurfaceVariant)
                    .environment(\.layoutDirection, .leftToRight)
            }

            VelroField(
                label: strings["auth.field.code"],
                text: $model.code,
                keyboard: .numberPad,
                contentType: .oneTimeCode,
                large: true,
                identifier: "signin.code"
            )

            PrimaryButton(
                label: strings["auth.action.sign_in"],
                enabled: model.canSubmitCode,
                loading: model.isSubmitting,
                pill: true
            ) {
                Task { await model.submitCode() }
            }
            .accessibilityIdentifier("signin.submit")

            HStack {
                TextAction(label: strings["common.action.back"]) { model.back() }
                Spacer()
                TextAction(
                    label: model.canResend
                        ? strings["auth.action.resend_code"]
                        : strings["auth.action.resend_code_in", ["seconds": model.resendAfterSeconds]],
                    enabled: model.canResend
                ) {
                    Task { await model.requestCode() }
                }
                .monospacedDigit()
            }
        }
    }
}
