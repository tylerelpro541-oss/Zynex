-- PET Finder - Zynex
-- Panel visual para Roblox
-- Requiere ejecutarse en un entorno compatible con Roblox Lua.

local Players = game:GetService("Players")
local HttpService = game:GetService("HttpService")

local player = Players.LocalPlayer
local URL = "https://zynex-kf4o.onrender.com/reports"

local gui = Instance.new("ScreenGui")
gui.Name = "PETFinder"
gui.ResetOnSpawn = false

local frame = Instance.new("Frame")
frame.Size = UDim2.new(0, 320, 0, 330)
frame.Position = UDim2.new(0.5, -160, 0.5, -165)
frame.BackgroundColor3 = Color3.fromRGB(15, 15, 20)
frame.BorderSizePixel = 0
frame.Active = true
frame.Draggable = true
frame.Parent = gui

local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 12)
corner.Parent = frame

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, -20, 0, 40)
title.Position = UDim2.new(0, 10, 0, 5)
title.BackgroundTransparency = 1
title.Text = "PET FINDER | ZYNEX"
title.TextColor3 = Color3.fromRGB(255, 70, 170)
title.TextScaled = true
title.Font = Enum.Font.GothamBold
title.Parent = frame

local filter = Instance.new("TextButton")
filter.Size = UDim2.new(1, -20, 0, 35)
filter.Position = UDim2.new(0, 10, 0, 50)
filter.BackgroundColor3 = Color3.fromRGB(45, 20, 40)
filter.TextColor3 = Color3.fromRGB(255, 130, 200)
filter.TextScaled = true
filter.Text = "FILTRO: ALL"
filter.Parent = frame

local search = Instance.new("TextButton")
search.Size = UDim2.new(1, -20, 0, 38)
search.Position = UDim2.new(0, 10, 0, 92)
search.BackgroundColor3 = Color3.fromRGB(210, 40, 130)
search.TextColor3 = Color3.new(1, 1, 1)
search.TextScaled = true
search.Font = Enum.Font.GothamBold
search.Text = "ACTUALIZAR REPORTES"
search.Parent = frame

local status = Instance.new("TextLabel")
status.Size = UDim2.new(1, -20, 0, 25)
status.Position = UDim2.new(0, 10, 0, 135)
status.BackgroundTransparency = 1
status.TextColor3 = Color3.fromRGB(230, 230, 230)
status.TextScaled = true
status.Text = "Listo"
status.Parent = frame

local results = Instance.new("TextLabel")
results.Size = UDim2.new(1, -20, 0, 145)
results.Position = UDim2.new(0, 10, 0, 165)
results.BackgroundColor3 = Color3.fromRGB(28, 28, 35)
results.TextColor3 = Color3.fromRGB(255, 255, 255)
results.TextXAlignment = Enum.TextXAlignment.Left
results.TextYAlignment = Enum.TextYAlignment.Top
results.TextWrapped = true
results.TextSize = 15
results.Text = "Pulsa ACTUALIZAR REPORTES"
results.Parent = frame

local rarities = {"ALL", "SECRET", "DIVINE", "ETERNAL"}
local rarityIndex = 1

filter.MouseButton1Click:Connect(function()
rarityIndex = rarityIndex % #rarities + 1
filter.Text = "FILTRO: " .. rarities[rarityIndex]
end)

local function refreshReports()
status.Text = "Consultando Render..."
results.Text = ""

local ok, response = pcall(function()
    return HttpService:GetAsync(
        URL .. "?rarity=" .. rarities[rarityIndex]
    )
end)

if not ok then
    status.Text = "No se pudo conectar"
    results.Text = "Revisa la compatibilidad HTTP del entorno."
    return
end

local decodedOk, data = pcall(function()
    return HttpService:JSONDecode(response)
end)

if not decodedOk or type(data) ~= "table" then
    status.Text = "Respuesta no válida"
    return
end

if #data == 0 then
    status.Text = "Sin reportes"
    results.Text = "Todavía no hay huevos para este filtro."
    return
end

local lines = {}
for i, report in ipairs(data) do
    if i > 6 then break end
    table.insert(lines,
        report.name .. " [" .. report.rarity .. "]"
    )
end

status.Text = "Reportes recibidos: " .. #data
results.Text = table.concat(lines, "\n")

end

search.MouseButton1Click:Connect(refreshReports)

gui.Parent = player:WaitForChild("PlayerGui")
