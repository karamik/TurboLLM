// ========================================================================
// key_obfuscation.sv – логическая обфускация и проверка аппаратного ключа
// Защита от внедрения закладок на этапе производства (TSMC / маски)
// ========================================================================

module key_obfuscation (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        key_valid,         // сигнал, что ключ загружен из eFuse
    input  logic [63:0] efuse_key,         // 64-битный ключ из eFuse (неизменяемый)
    input  logic        scan_mode,
    input  logic        test_mode,
    output logic        chip_unlocked,     // HIGH – чип активирован
    output logic        key_mismatch,      // HIGH – ключ не совпадает (блокировка)
    output logic        obfuscation_ok     // HIGH – обфускация пройдена
);

    // Секретный "золотой" ключ, зашитый в RTL (но обфусцированный)
    // В реальном проекте он не хранится в открытом виде, а вычисляется через запутанную логику
    // Здесь для примера – константа, но на практике это сложная функция от нескольких скрытых параметров
    localparam [63:0] GOLDEN_KEY = 64'hA5A5_A5A5_5A5A_5A5A;

    // Регистры для проверки
    logic [63:0] key_register;
    logic [63:0] obfuscated_golden;

    // Генерация обфусцированного ключа (запутанная логика)
    // Это лишь пример – в реальности используется многослойное перемешивание и зависимость от случайного seed
    always_comb begin
        // Простая обфускация: XOR с константой и перестановка бит
        obfuscated_golden = {GOLDEN_KEY[31:0], GOLDEN_KEY[63:32]} ^ 64'hF0F0_F0F0_0F0F_0F0F;
    end

    // Сравнение ключа с обфусцированным эталоном
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            key_register <= 64'h0;
            chip_unlocked <= 1'b0;
            key_mismatch <= 1'b0;
            obfuscation_ok <= 1'b0;
        end else if (scan_mode || test_mode) begin
            // В тестовых режимах обфускация отключается (для DFT)
            chip_unlocked <= 1'b1;
            key_mismatch <= 1'b0;
            obfuscation_ok <= 1'b1;
        end else begin
            // Загрузка ключа из eFuse
            if (key_valid) begin
                key_register <= efuse_key;
                // Сравнение с обфусцированным эталоном
                if (efuse_key == obfuscated_golden) begin
                    chip_unlocked <= 1'b1;
                    obfuscation_ok <= 1'b1;
                    key_mismatch <= 1'b0;
                end else begin
                    chip_unlocked <= 1'b0;
                    key_mismatch <= 1'b1;
                    obfuscation_ok <= 1'b0;
                end
            end
        end
    end

    // Анти-обход: если попытка подбора ключа (более N неудач) – блокировка навсегда
    // Реализуем счётчик неудачных попыток
    logic [3:0] fail_count;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fail_count <= 4'h0;
        end else if (key_valid && !chip_unlocked && !test_mode) begin
            fail_count <= fail_count + 1;
            if (fail_count >= 4'd10) begin
                // Блокировка чипа навсегда (можно использовать eFuse как "бит смерти")
                chip_unlocked <= 1'b0;
                key_mismatch <= 1'b1;
                // Тут можно сжечь eFuse-бит, чтобы даже после перезагрузки чип не разблокировался
            end
        end
    end

endmodule
