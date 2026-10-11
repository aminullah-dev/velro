import SwiftUI
import VelroCore

/// Sign in: the name, a drawn town with a car driving to its pin, then the
/// form straight on the page -- no card inside a card.
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
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.xl) {
                wordmark

                // The picture says what the app is for before a word is read:
                // a car, a road, a pin. It shrinks once the code is on its way,
                // so the field and the keyboard both fit.
                StreetMapArt()
                    .frame(height: model.step == .phone ? 200 : 120)
                    .clipShape(RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
                    .elevation(.low)

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

                VStack(spacing: Spacing.xs) {
                    // Help from the one screen a signed-out person can reach:
                    // a session that ran out in a valley with no data to renew
                    // it lands here, and the emergency numbers must too. Below
                    // the form -- a door out, not a step in it -- and without
                    // the report, which needs a token.
                    SecondaryButton(label: strings["safety.title"]) { helpOpen = true }
                        .accessibilityIdentifier("signin.help")

                    // What VELRO keeps, readable before handing over a number.
                    TextAction(label: strings["account.privacy"]) { openURL(app.privacyURL) }
                        .accessibilityIdentifier("signin.privacy")
                }
                .padding(.top, Spacing.sm)
            }
            .padding(.horizontal, Spacing.gutter)
            .padding(.top, Spacing.lg)
            .padding(.bottom, Spacing.lg)
            // A column on an unfolded phone, not a form stretched across it.
            .frame(maxWidth: Wide.readable)
            .frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(Palette.background)
        .animation(.snappy, value: model.step)
        .sheet(isPresented: $helpOpen) {
            HelpSheet(app: app, ride: nil, canReport: false)
        }
    }

    /// The name in the brand green and the promise under it, where a sign
    /// would carry them.
    private var wordmark: some View {
        VStack(alignment: .leading, spacing: Spacing.xxs) {
            Text(strings["app.name"])
                .velroFont(.display)
                .foregroundStyle(Palette.primary)
            Text(strings[AppFlavor.taglineKey])
                .velroFont(.label)
                .foregroundStyle(Palette.onSurfaceVariant)
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
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
                .velroFont(.headline)
                .foregroundStyle(Palette.onSurface)

            // Where the code goes, as two tabs: the choice is made once,
            // before the number, and a tab shows which one is live without
            // a tick to find.
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(strings["auth.channel.question"])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
                UnderlineTabs(
                    tabs: [
                        (API.channelSMS, strings["auth.channel.sms"], "message.fill"),
                        (API.channelTelegram, strings["auth.channel.telegram"], "paperplane.fill"),
                    ],
                    selection: $model.channel
                )
            }

            VelroField(
                label: strings["auth.field.phone"],
                text: $model.phone,
                placeholder: "0700 123 456",
                keyboard: .phonePad,
                contentType: .telephoneNumber,
                systemImage: "phone.fill",
                identifier: "signin.phone"
            )

            PrimaryButton(
                label: strings["auth.action.send_code"],
                enabled: model.canSubmitPhone,
                loading: model.isSubmitting
            ) {
                Task { await model.requestCode() }
            }
            .accessibilityIdentifier("signin.send")
            .padding(.top, Spacing.xs)
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
                .velroFont(.title, weight: .bold)
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
                systemImage: "lock.fill",
                identifier: "signin.code"
            )

            PrimaryButton(
                label: strings["auth.action.sign_in"],
                enabled: model.canSubmitCode,
                loading: model.isSubmitting
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

/// Two or three choices as tabs with a line under the chosen one: bold and
/// green when chosen, quiet when not. The line slides between them.
struct UnderlineTabs<Value: Hashable>: View {
    let tabs: [(value: Value, label: String, systemImage: String?)]
    @Binding var selection: Value
    @Namespace private var underline
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: 0) {
            ForEach(tabs.indices, id: \.self) { index in
                let tab = tabs[index]
                let chosen = tab.value == selection
                Button {
                    withAnimation(reduceMotion ? nil : .snappy) { selection = tab.value }
                } label: {
                    VStack(spacing: Spacing.sm) {
                        Label {
                            Text(tab.label).velroFont(.body, weight: chosen ? .bold : .regular)
                        } icon: {
                            if let systemImage = tab.systemImage {
                                Image(systemName: systemImage).font(.footnote.weight(.semibold))
                            }
                        }
                        .foregroundStyle(chosen ? Palette.primary : Palette.onSurfaceVariant)
                        ZStack {
                            Capsule().fill(Palette.outlineVariant).frame(height: 1)
                            if chosen {
                                Capsule().fill(Palette.primary).frame(height: 3)
                                    .matchedGeometryEffect(id: "underline", in: underline)
                            }
                        }
                        .frame(height: 3)
                    }
                    .frame(maxWidth: .infinity, minHeight: Sizing.touchTarget)
                    .contentShape(Rectangle())
                }
                .buttonStyle(PressStyle())
                .accessibilityAddTraits(chosen ? [.isSelected] : [])
            }
        }
    }
}
